using System;
using System.Collections.Generic;
using System.IO.Ports;
using System.Text.Json;
using System.Threading;
using ThingMagic;

class Program
{
    static volatile bool _run = true;
    static Reader? _r = null;
    static RFIDEventLogger? _logger = null;

    class TagState
    {
        public bool Present;
        public DateTime LastSeen;
    }

    static readonly object _tagLock = new object();
    static readonly Dictionary<string, TagState> _tags = new Dictionary<string, TagState>();

    // How long a tag must be unseen before we call it "gone"
    static readonly TimeSpan PresenceTimeout = TimeSpan.FromSeconds(5);

    static void Main()
    {
        // Graceful Ctrl+C handling
        Console.CancelKeyPress += (s, e) =>
        {
            e.Cancel = true;
            _run = false;
        };

        try
        {
            // ---- INITIALIZE LOGGER ----
            // Option 1: Log to file only
            _logger = new RFIDEventLogger("rfid_events.json");
            
            // Option 2: Log to file AND send to Pico via serial
            //_logger = new RFIDEventLogger("rfid_events.json", "com5", 115200);
            
            Console.WriteLine("Logger initialized");

            // ---- RFID READER SETUP ----
            _r = Reader.Create("tmr:///com7");   // change COM if needed
            _r.Connect();
            Console.WriteLine("Connected to RFID Reader");

            // ---- REGION SETUP ----
            Reader.Region currentRegion = (Reader.Region)_r.ParamGet("/reader/region/id");
            if (currentRegion == Reader.Region.UNSPEC)
            {
                Reader.Region[] supported =
                    (Reader.Region[])_r.ParamGet("/reader/region/supportedRegions");

                Reader.Region chosen = supported[0];
                foreach (var reg in supported)
                    if (reg == Reader.Region.NA) { chosen = reg; break; }

                _r.ParamSet("/reader/region/id", chosen);
                Console.WriteLine($"Region set to: {chosen}");
            }
            else
            {
                Console.WriteLine($"Region already set to: {currentRegion}");
            }

            // ---- PROTOCOL + POWER ----
            _r.ParamSet("/reader/tagop/protocol", TagProtocol.GEN2);
            _r.ParamSet("/reader/radio/readPower", 2500);
            Console.WriteLine($"RF Power: {_r.ParamGet("/reader/radio/readPower")}");

            // ---- READ PLAN ON ANT1 ----
            var plan = new SimpleReadPlan(new int[] { 1 }, TagProtocol.GEN2, null, null, 1000);
            _r.ParamSet("/reader/read/plan", plan);

            // ---- USER MEMORY MANAGER ----
            var userMem = new UserMemoryManager(_r!);

            Console.WriteLine("ENTER/LEAVE detection using blocking reads (5 s timeout).");
            Console.WriteLine("   On [ENTER], USER[0..3] will be read.");
            Console.WriteLine("   Press Q, 'end'+Enter, or Ctrl+C to stop.");

            // Main loop: poll tags + handle presence + key input
            while (_run)
            {
                // 1) Keyboard handling
                if (Console.KeyAvailable)
                {
                    var key = Console.ReadKey(intercept: true);

                    if (char.ToUpperInvariant(key.KeyChar) == 'Q')
                        _run = false;

                    if (key.Key == ConsoleKey.Enter && Console.In.Peek() >= 0)
                    {
                        var line = Console.ReadLine()?.Trim().ToLowerInvariant();
                        if (line == "end")
                            _run = false;
                    }
                }

                DateTime now = DateTime.Now;

                // 2) Blocking read (500 ms) – get current tags
                TagReadData[] tagsNow;
                try
                {
                    tagsNow = _r.Read(500);  // 0.5 s window
                }
                catch
                {
                    tagsNow = Array.Empty<TagReadData>();
                }

                lock (_tagLock)
                {
                    // 2a) Update states / fire ENTER for tags seen this cycle
                    foreach (var tr in tagsNow)
                    {
                        string epc = tr.Tag.EpcString;

                        if (!_tags.TryGetValue(epc, out var state))
                        {
                            state = new TagState { Present = false, LastSeen = now };
                            _tags[epc] = state;
                        }

                        bool wasPresent = state.Present;
                        state.LastSeen = now;

                        if (!wasPresent)
                        {
                            state.Present = true;
                            Console.WriteLine($"{now:HH:mm:ss}  [ENTER] EPC:{epc}");

                            // ---- READ USER MEMORY ON FIRST ENTER ----
                            string? userHex = null;
                            try
                            {
                                ushort[] userData = userMem.ReadUserWords(0, 4, epc);
                                userHex = UserMemoryManager.ToHexString(userData);
                                Console.WriteLine($"           USER[0..3] = {userHex}");
                            }
                            catch (Exception exUser)
                            {
                                Console.WriteLine($"           USER read failed: {exUser.Message}");
                            }

                            // ---- LOG ENTER EVENT ----
                            _logger?.LogEvent(new RFIDEvent
                            {
                                Timestamp = now,
                                EventType = "ENTER",
                                EPC = epc,
                                UserMemory = userHex,
                                RSSI = tr.Rssi,
                                AntennaId = tr.Antenna
                            });
                        }
                    }

                    // 2b) Fire LEAVE for tags that timed out
                    foreach (var kv in _tags)
                    {
                        string epc = kv.Key;
                        TagState state = kv.Value;

                        if (state.Present && (now - state.LastSeen) > PresenceTimeout)
                        {
                            state.Present = false;
                            Console.WriteLine($"{now:HH:mm:ss}  [LEAVE] EPC:{epc}");

                            // ---- LOG LEAVE EVENT ----
                            _logger?.LogEvent(new RFIDEvent
                            {
                                Timestamp = now,
                                EventType = "LEAVE",
                                EPC = epc
                            });
                        }
                    }
                }

                // Small sleep to avoid hammering CPU
                Thread.Sleep(50);
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("❌ " + ex.Message);
        }
        finally
        {
            try { _logger?.Close(); } catch { }
            try { _r?.Destroy(); } catch { }
            _r = null;
            Thread.Sleep(200);
            Console.WriteLine("Reader stopped and released. You can run again now.");
        }
    }
}

/// <summary>
/// Represents a single RFID event (ENTER or LEAVE)
/// </summary>
public class RFIDEvent
{
    public DateTime Timestamp { get; set; }
    public string EventType { get; set; } = "";  // "ENTER" or "LEAVE"
    public string EPC { get; set; } = "";
    public string? UserMemory { get; set; }
    public int? RSSI { get; set; }
    public int? AntennaId { get; set; }
}

/// <summary>
/// Logs RFID events to JSON file and optionally sends to Raspberry Pi Pico via serial
/// </summary>
public class RFIDEventLogger
{
    private readonly string _jsonFile;
    private readonly List<RFIDEvent> _events = new();
    private readonly SerialPort? _serialPort;
    private readonly object _lock = new object();

    /// <summary>
    /// Initialize logger with optional serial port for Raspberry Pi Pico
    /// </summary>
    /// <param name="jsonFile">Local JSON file path for backup/debugging</param>
    /// <param name="serialPort">COM port for Pico (e.g., "COM3"), or null for file-only</param>
    /// <param name="baudRate">Baud rate for serial communication</param>
    public RFIDEventLogger(string jsonFile, string? serialPort = null, int baudRate = 115200)
    {
        _jsonFile = jsonFile;

        // Overwrite previous file (start fresh)
        try
        {
            if (File.Exists(_jsonFile))
                File.Delete(_jsonFile);
            // or to keep a valid empty JSON array instead of deleting:
            // File.WriteAllText(_jsonFile, "[]");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Could not clear existing file: {ex.Message}");
        }

        // Setup serial connection to Pico if specified
        if (!string.IsNullOrEmpty(serialPort))
        {
            try
            {
                _serialPort = new SerialPort(serialPort, baudRate)
                {
                    DtrEnable = true,
                    RtsEnable = true,
                    NewLine = "\n"
                };
                _serialPort.Open();
                Console.WriteLine($"✅ Serial connection to Pico established on {serialPort}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Could not open serial port {serialPort}: {ex.Message}");
                _serialPort = null;
            }
        }
    }

    private void LoadExistingEvents()
    {
        if (File.Exists(_jsonFile))
        {
            try
            {
                var json = File.ReadAllText(_jsonFile);
                var events = JsonSerializer.Deserialize<List<RFIDEvent>>(json);
                if (events != null)
                {
                    _events.AddRange(events);
                    Console.WriteLine($"Loaded {events.Count} existing events from {_jsonFile}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Could not load existing events: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// Log a single RFID event
    /// </summary>
    public void LogEvent(RFIDEvent evt)
    {
        lock (_lock)
        {
            _events.Add(evt);

            // Save to local file
            SaveToFile();

            // Send to Pico via serial
            SendToPico(evt);
        }
    }

    private void SaveToFile()
    {
        try
        {
            var options = new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            };

            var json = JsonSerializer.Serialize(_events, options);
            File.WriteAllText(_jsonFile, json);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"⚠️  Error saving to file: {ex.Message}");
        }
    }

    private void SendToPico(RFIDEvent evt)
    {
        if (_serialPort == null || !_serialPort.IsOpen)
            return;

        try
        {
            var options = new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            };

            // Serialize single event as compact JSON
            var json = JsonSerializer.Serialize(evt, options);
            
            // Send to Pico (newline-delimited JSON)
            _serialPort.WriteLine(json);
            
            Console.WriteLine($"Sent to Pico: {json}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"⚠️  Error sending to Pico: {ex.Message}");
        }
    }

    /// <summary>
    /// Get all logged events
    /// </summary>
    public List<RFIDEvent> GetEvents() => new List<RFIDEvent>(_events);

    /// <summary>
    /// Get events within a time range
    /// </summary>
    public List<RFIDEvent> GetEventsByTimeRange(DateTime start, DateTime end)
    {
        return _events.FindAll(e => e.Timestamp >= start && e.Timestamp <= end);
    }

    /// <summary>
    /// Get all events for a specific EPC
    /// </summary>
    public List<RFIDEvent> GetEventsByEPC(string epc)
    {
        return _events.FindAll(e => e.EPC == epc);
    }

    /// <summary>
    /// Close serial connection and save final state
    /// </summary>
    public void Close()
    {
        lock (_lock)
        {
            SaveToFile();
            
            if (_serialPort != null && _serialPort.IsOpen)
            {
                _serialPort.Close();
                Console.WriteLine("✅ Serial port closed");
            }
        }
    }
}

/// <summary>
/// Helper class to access the USER memory bank of a Gen2 tag
/// using the ThingMagic MercuryAPI.
/// </summary>
class UserMemoryManager
{
    private readonly Reader _reader;

    public UserMemoryManager(Reader reader)
    {
        _reader = reader ?? throw new ArgumentNullException(nameof(reader));

        // Make sure tag operations use Gen2 protocol
        _reader.ParamSet("/reader/tagop/protocol", TagProtocol.GEN2);
    }

    /// <summary>
    /// Reads words from the USER memory bank of the tag with the given EPC.
    /// </summary>
    /// <param name="wordAddress">Word offset (0 = first USER word).</param>
    /// <param name="wordCount">Number of 16-bit words to read.</param>
    /// <param name="epcHex">
    /// EPC of the target tag as a hex string (no spaces), e.g. "300833B2DDD9014000000000".
    /// </param>
    /// <returns>Array of 16-bit words read from USER memory.</returns>
    public ushort[] ReadUserWords(ushort wordAddress, ushort wordCount, string epcHex)
    {
        if (string.IsNullOrWhiteSpace(epcHex))
            throw new ArgumentException("EPC must be non-empty", nameof(epcHex));
        if (wordCount == 0)
            throw new ArgumentOutOfRangeException(nameof(wordCount), "wordCount must be > 0");

        TagFilter filter = new TagData(epcHex);

        Gen2.ReadData op = new Gen2.ReadData(
            Gen2.Bank.USER,
            wordAddress,
            (byte)wordCount
        );

        object result = _reader.ExecuteTagOp(op, filter);
        return (ushort[])result;
    }

    /// <summary>
    /// Writes words into the USER memory bank of the tag with the given EPC.
    /// </summary>
    /// <param name="wordAddress">Word offset in USER memory to start writing.</param>
    /// <param name="dataWords">Data to write, as 16-bit words.</param>
    /// <param name="epcHex">Target tag EPC as hex string.</param>
    public void WriteUserWords(ushort wordAddress, ushort[] dataWords, string epcHex)
    {
        if (string.IsNullOrWhiteSpace(epcHex))
            throw new ArgumentException("EPC must be non-empty", nameof(epcHex));
        if (dataWords == null || dataWords.Length == 0)
            throw new ArgumentException("dataWords must be non-empty", nameof(dataWords));

        TagFilter filter = new TagData(epcHex);

        Gen2.WriteData op = new Gen2.WriteData(
            Gen2.Bank.USER,
            wordAddress,
            dataWords
        );

        _reader.ExecuteTagOp(op, filter);
    }

    /// <summary>
    /// Utility: convert an array of 16-bit words to a big-endian hex string.
    /// </summary>
    public static string ToHexString(ushort[] words)
    {
        if (words == null || words.Length == 0)
            return string.Empty;

        return string.Concat(Array.ConvertAll(words, w => w.ToString("X4")));
    }
}