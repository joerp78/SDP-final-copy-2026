package BLOSSM.service;

import org.springframework.stereotype.Service;
import BLOSSM.model.Plant;
import BLOSSM.model.ReadingJson;
import BLOSSM.repository.PlantRepository;

import java.time.LocalDateTime;
import java.util.*;

@Service
public class PlantService {

    private final PlantRepository repo;

    public PlantService(PlantRepository repo) {
        this.repo = repo;
    }

    // ═══════════════════════════════════════════════════
    //  REGISTRATION
    // ═══════════════════════════════════════════════════

    /**
     * Register a brand-new plant.
     * If no plantId is supplied, auto-assign the next available one.
     */
    public Plant register(Plant incoming) {
        // Auto-assign plantId if the caller didn't provide one
        if (incoming.getPlantId() == null) {
            List<Long> existing = repo.findDistinctPlantIds();
            long nextId = existing.isEmpty()
                    ? 1L
                    : Collections.max(existing) + 1;
            incoming.setPlantId(nextId);
        }

        // Prevent duplicate registration
        if (repo.existsByPlantId(incoming.getPlantId())) {
            // Return the existing latest row instead of creating a dupe
            return repo.findTopByPlantIdOrderByTimestampDesc(
                    incoming.getPlantId()).orElse(incoming);
        }

        // Stamp the registration time
        if (incoming.getTimestamp() == null) {
            incoming.setTimestamp(LocalDateTime.now());
        }

        return repo.save(incoming);
    }

    // ═══════════════════════════════════════════════════
    //  SAVING READINGS
    // ═══════════════════════════════════════════════════

    /**
     * Save a batch of sensor readings for a specific plant.
     * Fills in plantId and name automatically so the hub firmware
     * only needs to send temperature, moisture, conductivity, timestamp.
     */
    public List<Plant> saveReadings(Long plantId, List<Plant> readings) {
        // Look up the plant's name from its registration row
        String name = repo.findTopByPlantIdOrderByTimestampDesc(plantId)
                .map(Plant::getName)
                .orElse("Plant " + plantId);

        // Stamp each reading with the correct plantId and name
        for (Plant r : readings) {
            r.setPlantId(plantId);
            r.setName(name);

            if (r.getTimestamp() == null) {
                r.setTimestamp(LocalDateTime.now());
            }
        }

        return repo.saveAll(readings);
    }

    // ═══════════════════════════════════════════════════
    //  LATEST SNAPSHOTS
    // ═══════════════════════════════════════════════════

    /**
     * One Plant object per registered plant, each being the most
     * recent reading. This powers the overview card grid.
     *
     *  ┌────────┬────────┬──────┬──────────┐
     *  │plantId │ name   │ temp │ moisture │  ← latest row per plant
     *  ├────────┼────────┼──────┼──────────┤
     *  │   1    │ Basil  │ 24.0 │   42.1   │
     *  │   2    │ Tomato │ 25.6 │   37.2   │
     *  │   3    │ Fern   │ 21.0 │   62.5   │
     *  └────────┴────────┴──────┴──────────┘
     */
    public List<Plant> getAllLatest() {
        List<Long> plantIds = repo.findDistinctPlantIds();
        List<Plant> latest = new ArrayList<>();

        for (Long pid : plantIds) {
            repo.findTopByPlantIdOrderByTimestampDesc(pid)
                    .ifPresent(latest::add);
        }

        // Sort by plantId so the cards always appear in a stable order
        latest.sort(Comparator.comparing(Plant::getPlantId));
        return latest;
    }

    /**
     * Latest reading for a single plant.
     * Used on the detail page header and metric cards.
     */
    public Plant getById(Long plantId) {
        return repo.findTopByPlantIdOrderByTimestampDesc(plantId)
                .orElseThrow(() -> new NoSuchElementException(
                        "No plant found with plantId " + plantId));
    }

    // ═══════════════════════════════════════════════════
    //  HISTORICAL DATA (for Chart.js)
    // ═══════════════════════════════════════════════════

    /**
     * Historical readings for one plant, formatted for Chart.js.
     * Default: last 24 hours.
     */
    public ReadingJson getReadingsForPlant(Long plantId) {
        return getReadingsForPlant(plantId, 24);
    }

    /**
     * Historical readings for one plant within the given hour window.
     *
     * Returns a ReadingJson like:
     * {
     *   "labels":           ["08:00","08:05","08:10"],
     *   "temperature":      [22.5, 23.1, 23.8],
     *   "soilMoisture":     [45.0, 44.2, 43.5],
     *   "soilConductivity": [1.20, 1.25, 1.31]
     * }
     */
    public ReadingJson getReadingsForPlant(Long plantId, int hours) {
        LocalDateTime since = LocalDateTime.now().minusHours(hours);

        List<Plant> readings =
                repo.findByPlantIdAndTimestampAfterOrderByTimestampAsc(
                        plantId, since);

        if (readings.isEmpty()) {
            return ReadingJson.empty();
        }

        return ReadingJson.fromPlants(readings);
    }

    /**
     * Historical data for ALL plants, keyed by plantId (as a String).
     * This is serialised to JSON and injected into the dashboard's
     * <script> block so Chart.js can render every plant's graphs.
     *
     * Returns a map like:
     * {
     *   "1": { "labels":[...], "temperature":[...], ... },
     *   "2": { "labels":[...], "temperature":[...], ... }
     * }
     */
    public Map<String, ReadingJson> getHistoricalMap() {
        List<Long> plantIds = repo.findDistinctPlantIds();
        Map<String, ReadingJson> result = new LinkedHashMap<>();

        for (Long pid : plantIds) {
            result.put(
                    pid.toString(),
                    getReadingsForPlant(pid)
            );
        }

        return result;
    }
}