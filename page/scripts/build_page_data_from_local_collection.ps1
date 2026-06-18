param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$CollectionRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\data-analysis\00_data_collection\outputs")).Path
)

$ErrorActionPreference = "Stop"

$source = @"
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

public sealed class PageDataBuilder
{
    private readonly string repoRoot;
    private readonly string collectionRoot;
    private readonly string gasFinalRoot;
    private readonly string derivedRoot;
    private readonly string pageManualRoot;
    private readonly string pageLatestRoot;
    private readonly CultureInfo invariant = CultureInfo.InvariantCulture;
    private readonly Dictionary<string, double> latestGasoline = new Dictionary<string, double>();
    private readonly Dictionary<string, double> latestDiesel = new Dictionary<string, double>();
    private readonly List<RegionMetric> regionMetrics = new List<RegionMetric>();
    private readonly List<StationRow> stationRows = new List<StationRow>();
    private readonly List<CoverageRow> coverageRows = new List<CoverageRow>();
    private string globalDateMin;
    private string globalDateMax;
    private int processedFiles;

    private sealed class RegionMetric
    {
        public string Region;
        public string Fuel;
        public double ActualPrice;
        public string SourceDate;
        public long StationCount;
    }

    private sealed class StationRow
    {
        public string StationId;
        public string Name;
        public string Brand;
        public string Region;
        public string Address;
        public string Lon;
        public string Lat;
        public double? GasolinePrice;
        public double? DieselPrice;
    }

    private sealed class CoverageRow
    {
        public string Dataset;
        public string Date;
        public string Region;
        public long Value;
        public string Unit;
        public string Label;
    }

    private sealed class PriceAccumulator
    {
        public double Sum;
        public long Count;
    }

    public PageDataBuilder(string repoRoot, string collectionRoot)
    {
        this.repoRoot = repoRoot;
        this.collectionRoot = collectionRoot;
        gasFinalRoot = Path.Combine(collectionRoot, "gas_station_prices_by_region");
        derivedRoot = Path.Combine(collectionRoot, "derived_data");
        pageManualRoot = Path.Combine(repoRoot, "page", "manual_inputs");
        pageLatestRoot = Path.Combine(repoRoot, "page", "public", "data", "latest");
    }

    public static void Build(string repoRoot, string collectionRoot)
    {
        new PageDataBuilder(repoRoot, collectionRoot).Run();
    }

    private void Run()
    {
        Directory.CreateDirectory(pageManualRoot);
        Directory.CreateDirectory(pageLatestRoot);

        string priceHistoryCsv = Path.Combine(pageManualRoot, "price_history.csv");
        string priceHistoryJson = Path.Combine(pageLatestRoot, "price_history.json");
        using (StreamWriter csv = NewWriter(priceHistoryCsv))
        using (StreamWriter json = NewWriter(priceHistoryJson))
        {
            csv.WriteLine("date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy,source");
            json.Write("[");
            bool firstJson = true;

            foreach (DirectoryInfo dir in new DirectoryInfo(gasFinalRoot).EnumerateDirectories().OrderBy(d => CanonicalRegion(d.Name), StringComparer.Ordinal))
            {
                string region = CanonicalRegion(dir.Name);
                ProcessRegionFuel(dir, region, "gasoline", csv, json, ref firstJson);
                ProcessRegionFuel(dir, region, "diesel", csv, json, ref firstJson);
            }

            json.Write("]\n");
        }

        BuildStationRows();
        BuildFacilityCoverage();
        WriteRegionToday();
        WriteStationIndex();
        WriteTrainingCoverage();
        WriteNationalToday();
        WriteExternalStatus();
        WriteManifest();

        Console.WriteLine("[SUMMARY] processed_price_files=" + processedFiles);
        Console.WriteLine("[SUMMARY] date_min=" + (globalDateMin ?? ""));
        Console.WriteLine("[SUMMARY] date_max=" + (globalDateMax ?? ""));
        Console.WriteLine("[SUMMARY] region_today_rows=" + regionMetrics.Count);
        Console.WriteLine("[SUMMARY] station_search_rows=" + stationRows.Count);
        Console.WriteLine("[SUMMARY] coverage_rows=" + coverageRows.Count);
    }

    private void ProcessRegionFuel(DirectoryInfo dir, string region, string fuel, StreamWriter csv, StreamWriter json, ref bool firstJson)
    {
        string file = Path.Combine(dir.FullName, fuel + ".csv");
        if (File.Exists(file))
        {
            ProcessPriceFile(file, region, fuel, csv, json, ref firstJson);
            return;
        }

        string partsRoot = Path.Combine(dir.FullName, fuel + ".parts");
        if (Directory.Exists(partsRoot))
        {
            ProcessPriceParts(partsRoot, region, fuel, csv, json, ref firstJson);
        }
    }

    private void ProcessPriceFile(string file, string region, string fuel, StreamWriter csv, StreamWriter json, ref bool firstJson)
    {
        if (!File.Exists(file)) return;
        string sourcePath = PriceSourcePath(region, fuel, false);

        using (StreamReader reader = new StreamReader(file, Encoding.UTF8, true, 1024 * 1024))
        {
            string header = reader.ReadLine();
            if (String.IsNullOrWhiteSpace(header)) return;
            header = header.TrimStart('\uFEFF');
            string[] ids = header.Split(',').Skip(1).ToArray();
            string[] latestParts = null;
            string latestDate = null;
            string dateMin = null;
            string dateMax = null;
            long observations = 0;
            long rows = 0;

            string line;
            while ((line = reader.ReadLine()) != null)
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                string[] parts = line.Split(',');
                if (parts.Length < 2) continue;

                string date = parts[0];
                double sum = 0;
                long count = 0;
                for (int i = 1; i < parts.Length; i++)
                {
                    double value;
                    if (TryPrice(parts[i], out value))
                    {
                        sum += value;
                        count++;
                    }
                }

                if (count > 0)
                {
                    double average = Math.Round(sum / count, 1);
                    WritePriceHistoryCsv(csv, date, region, fuel, average, sourcePath);
                    WritePriceHistoryJson(json, ref firstJson, date, region, fuel, average, sourcePath);
                    observations += count;
                }

                if (dateMin == null || String.CompareOrdinal(date, dateMin) < 0) dateMin = date;
                if (dateMax == null || String.CompareOrdinal(date, dateMax) > 0) dateMax = date;
                latestDate = date;
                latestParts = parts;
                rows++;
            }

            double latestSum = 0;
            long latestCount = 0;
            if (latestParts != null)
            {
                for (int i = 1; i < latestParts.Length && i - 1 < ids.Length; i++)
                {
                    double value;
                    if (TryPrice(latestParts[i], out value))
                    {
                        string stationId = ids[i - 1];
                        if (fuel == "gasoline") latestGasoline[stationId] = value;
                        else latestDiesel[stationId] = value;
                        latestSum += value;
                        latestCount++;
                    }
                }
            }

            if (latestCount > 0)
            {
                regionMetrics.Add(new RegionMetric {
                    Region = region,
                    Fuel = fuel,
                    ActualPrice = Math.Round(latestSum / latestCount, 1),
                    SourceDate = latestDate,
                    StationCount = latestCount
                });
            }

            coverageRows.Add(new CoverageRow {
                Dataset = fuel + "_price_observations",
                Date = dateMax,
                Region = region,
                Value = observations,
                Unit = "건",
                Label = fuel == "gasoline" ? "휘발유 가격 관측 수" : "경유 가격 관측 수"
            });
            coverageRows.Add(new CoverageRow {
                Dataset = fuel + "_latest_station_count",
                Date = latestDate,
                Region = region,
                Value = latestCount,
                Unit = "개",
                Label = fuel == "gasoline" ? "최신 휘발유 가격 주유소 수" : "최신 경유 가격 주유소 수"
            });

            if (dateMin != null && (globalDateMin == null || String.CompareOrdinal(dateMin, globalDateMin) < 0)) globalDateMin = dateMin;
            if (dateMax != null && (globalDateMax == null || String.CompareOrdinal(dateMax, globalDateMax) > 0)) globalDateMax = dateMax;
            processedFiles++;
            Console.WriteLine("[PRICE] " + region + " " + fuel + " rows=" + rows + " latest=" + latestCount + " obs=" + observations);
        }
    }

    private void ProcessPriceParts(string partsRoot, string region, string fuel, StreamWriter csv, StreamWriter json, ref bool firstJson)
    {
        Dictionary<string, PriceAccumulator> byDate = new Dictionary<string, PriceAccumulator>();
        Dictionary<string, double> latestValues = new Dictionary<string, double>();
        string latestDate = null;
        string dateMin = null;
        string dateMax = null;
        long observations = 0;
        long rows = 0;

        foreach (string file in Directory.EnumerateFiles(partsRoot, "part-*.csv").OrderBy(p => p, StringComparer.Ordinal))
        {
            using (StreamReader reader = new StreamReader(file, Encoding.UTF8, true, 1024 * 1024))
            {
                string header = reader.ReadLine();
                if (String.IsNullOrWhiteSpace(header)) continue;
                header = header.TrimStart('\uFEFF');
                string[] ids = header.Split(',').Skip(1).ToArray();
                string[] partLatestParts = null;
                string partLatestDate = null;

                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (String.IsNullOrWhiteSpace(line)) continue;
                    string[] parts = line.Split(',');
                    if (parts.Length < 2) continue;

                    string date = parts[0];
                    PriceAccumulator acc;
                    if (!byDate.TryGetValue(date, out acc))
                    {
                        acc = new PriceAccumulator();
                        byDate[date] = acc;
                    }

                    for (int i = 1; i < parts.Length; i++)
                    {
                        double value;
                        if (TryPrice(parts[i], out value))
                        {
                            acc.Sum += value;
                            acc.Count++;
                            observations++;
                        }
                    }

                    if (dateMin == null || String.CompareOrdinal(date, dateMin) < 0) dateMin = date;
                    if (dateMax == null || String.CompareOrdinal(date, dateMax) > 0) dateMax = date;
                    partLatestDate = date;
                    partLatestParts = parts;
                    rows++;
                }

                if (partLatestDate != null && partLatestParts != null)
                {
                    if (latestDate == null || String.CompareOrdinal(partLatestDate, latestDate) > 0)
                    {
                        latestDate = partLatestDate;
                        latestValues.Clear();
                    }

                    if (String.CompareOrdinal(partLatestDate, latestDate) == 0)
                    {
                        for (int i = 1; i < partLatestParts.Length && i - 1 < ids.Length; i++)
                        {
                            double value;
                            if (TryPrice(partLatestParts[i], out value))
                            {
                                latestValues[ids[i - 1]] = value;
                            }
                        }
                    }
                }
            }
        }

        string sourcePath = PriceSourcePath(region, fuel, true);
        foreach (KeyValuePair<string, PriceAccumulator> item in byDate.OrderBy(kv => kv.Key, StringComparer.Ordinal))
        {
            if (item.Value.Count <= 0) continue;
            double average = Math.Round(item.Value.Sum / item.Value.Count, 1);
            WritePriceHistoryCsv(csv, item.Key, region, fuel, average, sourcePath);
            WritePriceHistoryJson(json, ref firstJson, item.Key, region, fuel, average, sourcePath);
        }

        foreach (KeyValuePair<string, double> item in latestValues)
        {
            if (fuel == "gasoline") latestGasoline[item.Key] = item.Value;
            else latestDiesel[item.Key] = item.Value;
        }

        long latestCount = latestValues.Count;
        if (latestCount > 0)
        {
            regionMetrics.Add(new RegionMetric {
                Region = region,
                Fuel = fuel,
                ActualPrice = Math.Round(latestValues.Values.Sum() / latestCount, 1),
                SourceDate = latestDate,
                StationCount = latestCount
            });
        }

        coverageRows.Add(new CoverageRow {
            Dataset = fuel + "_price_observations",
            Date = dateMax,
            Region = region,
            Value = observations,
            Unit = "건",
            Label = fuel == "gasoline" ? "휘발유 가격 관측 수" : "경유 가격 관측 수"
        });
        coverageRows.Add(new CoverageRow {
            Dataset = fuel + "_latest_station_count",
            Date = latestDate,
            Region = region,
            Value = latestCount,
            Unit = "개",
            Label = fuel == "gasoline" ? "최신 휘발유 가격 주유소 수" : "최신 경유 가격 주유소 수"
        });

        if (dateMin != null && (globalDateMin == null || String.CompareOrdinal(dateMin, globalDateMin) < 0)) globalDateMin = dateMin;
        if (dateMax != null && (globalDateMax == null || String.CompareOrdinal(dateMax, globalDateMax) > 0)) globalDateMax = dateMax;
        if (byDate.Count > 0) processedFiles++;
        Console.WriteLine("[PRICE] " + region + " " + fuel + " part_rows=" + rows + " latest=" + latestCount + " obs=" + observations);
    }

    private void BuildStationRows()
    {
        string profilePath = Path.Combine(derivedRoot, "station_latest_profile.csv");
        Dictionary<string, long> stationCountByRegion = new Dictionary<string, long>();

        foreach (Dictionary<string, string> row in ReadCsvObjects(profilePath))
        {
            string coordValid = Get(row, "coord_valid").ToLowerInvariant();
            if (coordValid != "true") continue;

            string stationId = Get(row, "station_id");
            if (String.IsNullOrWhiteSpace(stationId)) continue;

            double gas;
            double diesel;
            bool hasGas = latestGasoline.TryGetValue(stationId, out gas);
            bool hasDiesel = latestDiesel.TryGetValue(stationId, out diesel);
            if (!hasGas && !hasDiesel) continue;

            string region = CanonicalRegion(FirstNonEmpty(Get(row, "source_region"), Get(row, "region"), Get(row, "address")));
            stationRows.Add(new StationRow {
                StationId = stationId,
                Name = Get(row, "station_name"),
                Brand = Get(row, "brand"),
                Region = region,
                Address = Get(row, "address"),
                Lon = Get(row, "lon"),
                Lat = Get(row, "lat"),
                GasolinePrice = hasGas ? (double?)gas : null,
                DieselPrice = hasDiesel ? (double?)diesel : null
            });

            if (!stationCountByRegion.ContainsKey(region)) stationCountByRegion[region] = 0;
            stationCountByRegion[region]++;
        }

        foreach (KeyValuePair<string, long> item in stationCountByRegion)
        {
            coverageRows.Add(new CoverageRow {
                Dataset = "station_count",
                Date = globalDateMax,
                Region = item.Key,
                Value = item.Value,
                Unit = "개",
                Label = "주유소 입력 수"
            });
        }
    }

    private void BuildFacilityCoverage()
    {
        string facilityPath = Path.Combine(derivedRoot, "facility_points.csv");
        if (!File.Exists(facilityPath)) return;

        Dictionary<string, long> countByRegion = new Dictionary<string, long>();
        foreach (Dictionary<string, string> row in ReadCsvObjects(facilityPath))
        {
            if (Get(row, "coord_valid").ToLowerInvariant() != "true") continue;
            string region = CanonicalRegion(Get(row, "address"));
            if (String.IsNullOrWhiteSpace(region)) continue;
            if (!countByRegion.ContainsKey(region)) countByRegion[region] = 0;
            countByRegion[region]++;
        }

        foreach (KeyValuePair<string, long> item in countByRegion)
        {
            coverageRows.Add(new CoverageRow {
                Dataset = "facility_count",
                Date = globalDateMax,
                Region = item.Key,
                Value = item.Value,
                Unit = "개",
                Label = "시설 영향력 입력 수"
            });
        }
    }

    private void WriteRegionToday()
    {
        string csvPath = Path.Combine(pageManualRoot, "region_today.csv");
        string jsonPath = Path.Combine(pageLatestRoot, "region_today.json");
        List<RegionMetric> rows = regionMetrics.OrderBy(r => r.Region, StringComparer.Ordinal).ThenBy(r => r.Fuel, StringComparer.Ordinal).ToList();

        using (StreamWriter csv = NewWriter(csvPath))
        {
            csv.WriteLine("region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy,judge_policy,source_date,station_count");
            foreach (RegionMetric row in rows)
            {
                csv.WriteLine(String.Join(",", new string[] {
                    Csv(row.Region),
                    Csv(row.Fuel),
                    Csv(Number(row.ActualPrice)),
                    "",
                    "",
                    "",
                    "",
                    "",
                    Csv(row.SourceDate),
                    Csv(row.StationCount.ToString(invariant))
                }));
            }
        }

        using (StreamWriter json = NewWriter(jsonPath))
        {
            json.Write("[\n");
            bool firstRegion = true;
            foreach (IGrouping<string, RegionMetric> group in rows.GroupBy(r => r.Region).OrderBy(g => g.Key, StringComparer.Ordinal))
            {
                if (!firstRegion) json.Write(",\n");
                firstRegion = false;
                json.Write("  {\"region\":");
                JsonString(json, group.Key);
                foreach (RegionMetric metric in group.OrderBy(g => g.Fuel, StringComparer.Ordinal))
                {
                    json.Write(",\"");
                    json.Write(metric.Fuel);
                    json.Write("\":{\"actual_price\":");
                    json.Write(Number(metric.ActualPrice));
                    json.Write(",\"fair_price_policy\":null,\"band_low_policy\":null,\"band_high_policy\":null,\"gap_policy\":null,\"judge_policy\":null,\"source_date\":");
                    JsonString(json, metric.SourceDate);
                    json.Write(",\"station_count\":");
                    json.Write(metric.StationCount.ToString(invariant));
                    json.Write("}");
                }
                json.Write("}");
            }
            json.Write("\n]\n");
        }
    }

    private void WriteStationIndex()
    {
        string csvPath = Path.Combine(pageManualRoot, "station_search_index.csv");
        string jsonPath = Path.Combine(pageLatestRoot, "station_search_index.json");
        List<StationRow> rows = stationRows
            .OrderBy(s => s.Region, StringComparer.Ordinal)
            .ThenBy(s => s.Name, StringComparer.Ordinal)
            .ThenBy(s => s.StationId, StringComparer.Ordinal)
            .ToList();

        using (StreamWriter csv = NewWriter(csvPath))
        {
            csv.WriteLine("station_id,name,brand,region,address,lon,lat,gasoline_price,diesel_price,judge_policy");
            foreach (StationRow row in rows)
            {
                csv.WriteLine(String.Join(",", new string[] {
                    Csv(row.StationId),
                    Csv(row.Name),
                    Csv(row.Brand),
                    Csv(row.Region),
                    Csv(row.Address),
                    Csv(row.Lon),
                    Csv(row.Lat),
                    Csv(row.GasolinePrice.HasValue ? Number(row.GasolinePrice.Value) : ""),
                    Csv(row.DieselPrice.HasValue ? Number(row.DieselPrice.Value) : ""),
                    ""
                }));
            }
        }

        using (StreamWriter json = NewWriter(jsonPath))
        {
            json.Write("[\n");
            bool first = true;
            foreach (StationRow row in rows)
            {
                if (!first) json.Write(",\n");
                first = false;
                json.Write("  {\"station_id\":"); JsonString(json, row.StationId);
                json.Write(",\"name\":"); JsonString(json, row.Name);
                json.Write(",\"brand\":"); JsonString(json, row.Brand);
                json.Write(",\"region\":"); JsonString(json, row.Region);
                json.Write(",\"address\":"); JsonString(json, row.Address);
                json.Write(",\"lon\":"); json.Write(NullableNumber(row.Lon));
                json.Write(",\"lat\":"); json.Write(NullableNumber(row.Lat));
                json.Write(",\"gasoline_price\":"); json.Write(row.GasolinePrice.HasValue ? Number(row.GasolinePrice.Value) : "null");
                json.Write(",\"diesel_price\":"); json.Write(row.DieselPrice.HasValue ? Number(row.DieselPrice.Value) : "null");
                json.Write(",\"judge_policy\":null}");
            }
            json.Write("\n]\n");
        }
    }

    private void WriteTrainingCoverage()
    {
        string csvPath = Path.Combine(pageManualRoot, "training_data_coverage.csv");
        string jsonPath = Path.Combine(pageLatestRoot, "training_data_coverage.json");
        List<CoverageRow> rows = coverageRows
            .OrderBy(r => r.Dataset, StringComparer.Ordinal)
            .ThenBy(r => r.Date, StringComparer.Ordinal)
            .ThenBy(r => r.Region, StringComparer.Ordinal)
            .ToList();

        using (StreamWriter csv = NewWriter(csvPath))
        {
            csv.WriteLine("dataset,date,region,value,unit,label");
            foreach (CoverageRow row in rows)
            {
                csv.WriteLine(String.Join(",", new string[] {
                    Csv(row.Dataset),
                    Csv(row.Date),
                    Csv(row.Region),
                    Csv(row.Value.ToString(invariant)),
                    Csv(row.Unit),
                    Csv(row.Label)
                }));
            }
        }

        using (StreamWriter json = NewWriter(jsonPath))
        {
            json.Write("{\"schema_version\":\"training_data_coverage_v1\",\"generated_at\":");
            JsonString(json, GeneratedAt());
            json.Write(",\"source\":\"page/manual_inputs/training_data_coverage.csv\",\"datasets\":[");
            WriteDataset(json, rows, "station_count", "주유소 입력 수", "개", "data-analysis/00_data_collection/outputs/derived_data/station_latest_profile.csv + data-analysis/00_data_collection/outputs/gas_station_prices_by_region", "좌표가 유효하고 최신 가격이 붙은 주유소 수를 시도별로 집계했습니다.", true);
            WriteDataset(json, rows, "facility_count", "시설 영향력 입력 수", "개", "data-analysis/00_data_collection/outputs/derived_data/facility_points.csv", "좌표가 유효한 시설 데이터를 주소 기준 시도로 집계했습니다.", false);
            WriteDataset(json, rows, "gasoline_price_observations", "휘발유 가격 관측 수", "건", "data-analysis/00_data_collection/outputs/gas_station_prices_by_region/{시도}/gasoline.csv 또는 gasoline.parts", "원천 가격 행렬에서 0과 결측을 제외한 휘발유 관측 수입니다.", false);
            WriteDataset(json, rows, "diesel_price_observations", "경유 가격 관측 수", "건", "data-analysis/00_data_collection/outputs/gas_station_prices_by_region/{시도}/diesel.csv 또는 diesel.parts", "원천 가격 행렬에서 0과 결측을 제외한 경유 관측 수입니다.", false);
            WriteDataset(json, rows, "gasoline_latest_station_count", "최신 휘발유 가격 주유소 수", "개", "data-analysis/00_data_collection/outputs/gas_station_prices_by_region/{시도}/gasoline.csv 또는 gasoline.parts", "최신일에 휘발유 가격이 존재하는 주유소 수입니다.", false);
            WriteDataset(json, rows, "diesel_latest_station_count", "최신 경유 가격 주유소 수", "개", "data-analysis/00_data_collection/outputs/gas_station_prices_by_region/{시도}/diesel.csv 또는 diesel.parts", "최신일에 경유 가격이 존재하는 주유소 수입니다.", false);
            json.Write("],\"rows\":[");
            bool first = true;
            foreach (CoverageRow row in rows)
            {
                if (!first) json.Write(",");
                first = false;
                json.Write("{\"dataset\":"); JsonString(json, row.Dataset);
                json.Write(",\"date\":"); JsonString(json, row.Date);
                json.Write(",\"region\":"); JsonString(json, row.Region);
                json.Write(",\"value\":"); json.Write(row.Value.ToString(invariant));
                json.Write(",\"unit\":"); JsonString(json, row.Unit);
                json.Write(",\"label\":"); JsonString(json, row.Label);
                json.Write("}");
            }
            json.Write("]}\n");
        }
    }

    private void WriteDataset(StreamWriter json, List<CoverageRow> rows, string id, string label, string unit, string path, string note, bool first)
    {
        List<CoverageRow> selected = rows.Where(r => r.Dataset == id).ToList();
        List<string> dates = selected.Select(r => r.Date).Where(d => !String.IsNullOrWhiteSpace(d)).Distinct().OrderBy(d => d, StringComparer.Ordinal).ToList();
        if (!first) json.Write(",");
        json.Write("{\"id\":"); JsonString(json, id);
        json.Write(",\"label\":"); JsonString(json, label);
        json.Write(",\"unit\":"); JsonString(json, unit);
        json.Write(",\"status\":"); JsonString(json, selected.Count > 0 ? "connected" : "waiting");
        json.Write(",\"rows\":"); json.Write(selected.Count.ToString(invariant));
        json.Write(",\"date_min\":"); if (dates.Count > 0) JsonString(json, dates.First()); else json.Write("null");
        json.Write(",\"date_max\":"); if (dates.Count > 0) JsonString(json, dates.Last()); else json.Write("null");
        json.Write(",\"path\":"); JsonString(json, path);
        json.Write(",\"note\":"); JsonString(json, note);
        json.Write("}");
    }

    private void WriteNationalToday()
    {
        string file = Path.Combine(pageLatestRoot, "national_today.json");
        using (StreamWriter json = NewWriter(file))
        {
            json.Write("{\"schema_version\":\"national_today_v1\",\"as_of_date\":");
            JsonString(json, globalDateMax);
            json.Write(",\"generated_at\":"); JsonString(json, GeneratedAt());
            json.Write(",\"freshness\":\"sample\",\"fuels\":{");
            WriteSampleFuel(json, "gasoline", "휘발유", true);
            WriteSampleFuel(json, "diesel", "경유", false);
            json.Write("},\"policies\":[],\"errors\":{}}\n");
        }
    }

    private void WriteSampleFuel(StreamWriter json, string id, string label, bool first)
    {
        if (!first) json.Write(",");
        json.Write("\""); json.Write(id); json.Write("\":{\"label\":"); JsonString(json, label);
        json.Write(",\"actual_price\":1500,\"actual_delta_1d\":0,\"fair_price_policy\":1400,\"band_low_policy\":1380,\"band_high_policy\":1420,\"gap_policy\":100,\"judge_policy\":\"비쌈\",\"policy_effect\":0}");
    }

    private void WriteExternalStatus()
    {
        string file = Path.Combine(pageLatestRoot, "external_data_status.json");
        using (StreamWriter json = NewWriter(file))
        {
            json.Write("{\"schema_version\":\"external_data_status_v1\",\"generated_at\":");
            JsonString(json, GeneratedAt());
            json.Write(",\"datasets\":[");
            WriteStatus(json, true, "national_today", "전국 가격 요약", "connected", 2, globalDateMax, globalDateMax, "page/public/data/latest/national_today.json", "현재 지도 가격 표시는 요청에 따라 1500/1400 샘플 고정값입니다.");
            WriteStatus(json, false, "region_today", "지역별 최신 실제 가격", "connected", regionMetrics.Count, globalDateMax, globalDateMax, "page/manual_inputs/region_today.csv", "대용량 주유소 가격 원천에서 최신일 시도별 평균 실제 가격을 집계했습니다. 적정가는 AI 모델 완료 후 연결합니다.");
            WriteStatus(json, false, "station_search_index", "주유소 검색 인덱스", "connected", stationRows.Count, globalDateMax, globalDateMax, "page/manual_inputs/station_search_index.csv", "좌표가 있고 최신 휘발유/경유 가격 중 하나 이상이 존재하는 주유소만 포함했습니다.");
            WriteStatus(json, false, "price_history", "기간별 지역 평균 실제 가격", "connected", EstimateHistoryRows(), globalDateMin, globalDateMax, "page/manual_inputs/price_history.csv", "전체기간 시도별 평균 실제 가격입니다. 적정가격/범위는 AI 모델 결과가 나온 뒤 결합합니다.");
            WriteStatus(json, false, "training_data_coverage", "외부/학습 입력 데이터 현황", "connected", coverageRows.Count, globalDateMax, globalDateMax, "page/manual_inputs/training_data_coverage.csv", "AI 학습 입력 데이터의 지역별 분포를 지도에 칠하기 위한 요약입니다.");
            WriteStatus(json, false, "ai_model_outputs", "AI 적정가격 모델", "waiting", 0, null, null, "ai-model/03_prediction_model_design/outputs/{fuel}/", "모델 학습 완료 후 지역/주유소별 적정가격 예측 결과를 연결해야 합니다.");
            json.Write("]}\n");
        }
    }

    private long EstimateHistoryRows()
    {
        string file = Path.Combine(pageManualRoot, "price_history.csv");
        if (!File.Exists(file)) return 0;
        long rows = 0;
        using (StreamReader reader = new StreamReader(file, Encoding.UTF8, true, 1024 * 1024))
        {
            while (reader.ReadLine() != null) rows++;
        }
        return Math.Max(0, rows - 1);
    }

    private void WriteStatus(StreamWriter json, bool first, string id, string label, string status, long rows, string dateMin, string dateMax, string path, string note)
    {
        if (!first) json.Write(",");
        json.Write("{\"id\":"); JsonString(json, id);
        json.Write(",\"label\":"); JsonString(json, label);
        json.Write(",\"status\":"); JsonString(json, status);
        json.Write(",\"rows\":"); json.Write(rows.ToString(invariant));
        json.Write(",\"date_min\":"); if (dateMin == null) json.Write("null"); else JsonString(json, dateMin);
        json.Write(",\"date_max\":"); if (dateMax == null) json.Write("null"); else JsonString(json, dateMax);
        json.Write(",\"path\":"); JsonString(json, path);
        json.Write(",\"note\":"); JsonString(json, note);
        json.Write("}");
    }

    private void WriteManifest()
    {
        string file = Path.Combine(pageLatestRoot, "site_manifest.json");
        using (StreamWriter json = NewWriter(file))
        {
            json.Write("{\"schema_version\":\"page_data_v1\",\"as_of_date\":");
            JsonString(json, globalDateMax);
            json.Write(",\"generated_at\":"); JsonString(json, GeneratedAt());
            json.Write(",\"freshness\":\"sample\",\"files\":[\"national_today.json\",\"region_today.json\",\"station_search_index.json\",\"price_history.json\",\"training_data_coverage.json\",\"external_data_status.json\"],\"assets\":[\"korea-provinces.geojson\"],\"source\":{\"national\":\"page/public/data/latest/national_today.json\",\"region\":\"page/manual_inputs/region_today.csv\",\"station\":\"page/manual_inputs/station_search_index.csv\",\"history\":\"page/manual_inputs/price_history.csv\",\"training_coverage\":\"page/manual_inputs/training_data_coverage.csv\"}}\n");
        }
    }

    private string PriceSourcePath(string region, string fuel, bool splitParts)
    {
        string suffix = splitParts ? fuel + ".parts/" : fuel + ".csv";
        return "data-analysis/00_data_collection/outputs/gas_station_prices_by_region/" + region + "/" + suffix;
    }

    private void WritePriceHistoryCsv(StreamWriter csv, string date, string region, string fuel, double actualPrice, string sourcePath)
    {
        csv.Write(Csv(date)); csv.Write(",");
        csv.Write(Csv(region)); csv.Write(",");
        csv.Write(Csv(fuel)); csv.Write(",");
        csv.Write(Number(actualPrice)); csv.Write(",,,,");
        csv.Write(Csv(sourcePath));
        csv.WriteLine();
    }

    private void WritePriceHistoryJson(StreamWriter json, ref bool first, string date, string region, string fuel, double actualPrice, string sourcePath)
    {
        if (!first) json.Write(",");
        first = false;
        json.Write("{\"date\":"); JsonString(json, date);
        json.Write(",\"region\":"); JsonString(json, region);
        json.Write(",\"fuel\":"); JsonString(json, fuel);
        json.Write(",\"actual_price\":"); json.Write(Number(actualPrice));
        json.Write(",\"fair_price_policy\":null,\"band_low_policy\":null,\"band_high_policy\":null,\"gap_policy\":null,\"source\":");
        JsonString(json, sourcePath);
        json.Write("}");
    }

    private IEnumerable<Dictionary<string, string>> ReadCsvObjects(string file)
    {
        using (StreamReader reader = new StreamReader(file, Encoding.UTF8, true, 1024 * 1024))
        {
            string headerLine = reader.ReadLine();
            if (headerLine == null) yield break;
            string[] headers = ParseCsvLine(headerLine.TrimStart('\uFEFF')).ToArray();
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                List<string> values = ParseCsvLine(line);
                Dictionary<string, string> row = new Dictionary<string, string>();
                for (int i = 0; i < headers.Length; i++)
                {
                    row[headers[i]] = i < values.Count ? values[i] : "";
                }
                yield return row;
            }
        }
    }

    private static List<string> ParseCsvLine(string line)
    {
        List<string> cells = new List<string>();
        StringBuilder cell = new StringBuilder();
        bool quoted = false;
        for (int i = 0; i < line.Length; i++)
        {
            char ch = line[i];
            if (quoted)
            {
                if (ch == '"')
                {
                    if (i + 1 < line.Length && line[i + 1] == '"')
                    {
                        cell.Append('"');
                        i++;
                    }
                    else
                    {
                        quoted = false;
                    }
                }
                else
                {
                    cell.Append(ch);
                }
            }
            else if (ch == '"')
            {
                quoted = true;
            }
            else if (ch == ',')
            {
                cells.Add(cell.ToString());
                cell.Length = 0;
            }
            else
            {
                cell.Append(ch);
            }
        }
        cells.Add(cell.ToString());
        return cells;
    }

    private bool TryPrice(string text, out double value)
    {
        value = 0;
        return !String.IsNullOrWhiteSpace(text)
            && Double.TryParse(text, NumberStyles.Float, invariant, out value)
            && value > 0;
    }

    private static string Get(Dictionary<string, string> row, string key)
    {
        string value;
        return row.TryGetValue(key, out value) ? value : "";
    }

    private static string FirstNonEmpty(params string[] values)
    {
        foreach (string value in values)
        {
            if (!String.IsNullOrWhiteSpace(value)) return value;
        }
        return "";
    }

    private static string CanonicalRegion(string value)
    {
        if (String.IsNullOrWhiteSpace(value)) return "";
        string text = value.Normalize(NormalizationForm.FormC).Trim();
        if (text.StartsWith("서울")) return "서울";
        if (text.StartsWith("부산")) return "부산";
        if (text.StartsWith("대구")) return "대구";
        if (text.StartsWith("인천")) return "인천";
        if (text.StartsWith("광주")) return "광주";
        if (text.StartsWith("대전")) return "대전";
        if (text.StartsWith("울산")) return "울산";
        if (text.StartsWith("세종")) return "세종";
        if (text.StartsWith("경기")) return "경기";
        if (text.StartsWith("강원")) return "강원";
        if (text.StartsWith("충북") || text.StartsWith("충청북")) return "충북";
        if (text.StartsWith("충남") || text.StartsWith("충청남")) return "충남";
        if (text.StartsWith("전북") || text.StartsWith("전라북")) return "전북";
        if (text.StartsWith("전남") || text.StartsWith("전라남")) return "전남";
        if (text.StartsWith("경북") || text.StartsWith("경상북")) return "경북";
        if (text.StartsWith("경남") || text.StartsWith("경상남")) return "경남";
        if (text.StartsWith("제주")) return "제주";
        return text.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? text;
    }

    private static StreamWriter NewWriter(string file)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file));
        return new StreamWriter(file, false, new UTF8Encoding(false), 1024 * 1024);
    }

    private static string Csv(string value)
    {
        if (value == null) return "";
        if (value.IndexOfAny(new char[] { ',', '"', '\r', '\n' }) >= 0)
        {
            return "\"" + value.Replace("\"", "\"\"") + "\"";
        }
        return value;
    }

    private static string Number(double value)
    {
        return value.ToString("0.###", CultureInfo.InvariantCulture);
    }

    private static string NullableNumber(string value)
    {
        double parsed;
        return Double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed)
            ? parsed.ToString("0.########", CultureInfo.InvariantCulture)
            : "null";
    }

    private static void JsonString(StreamWriter writer, string value)
    {
        if (value == null)
        {
            writer.Write("null");
            return;
        }
        writer.Write('"');
        foreach (char ch in value)
        {
            switch (ch)
            {
                case '"': writer.Write("\\\""); break;
                case '\\': writer.Write("\\\\"); break;
                case '\b': writer.Write("\\b"); break;
                case '\f': writer.Write("\\f"); break;
                case '\n': writer.Write("\\n"); break;
                case '\r': writer.Write("\\r"); break;
                case '\t': writer.Write("\\t"); break;
                default:
                    if (Char.IsControl(ch)) writer.Write("\\u" + ((int)ch).ToString("x4"));
                    else writer.Write(ch);
                    break;
            }
        }
        writer.Write('"');
    }

    private static string GeneratedAt()
    {
        return DateTimeOffset.Now.ToString("yyyy-MM-ddTHH:mm:sszzz", CultureInfo.InvariantCulture);
    }
}
"@

Add-Type -TypeDefinition $source -Language CSharp
[PageDataBuilder]::Build((Resolve-Path $RepoRoot).Path, (Resolve-Path $CollectionRoot).Path)
