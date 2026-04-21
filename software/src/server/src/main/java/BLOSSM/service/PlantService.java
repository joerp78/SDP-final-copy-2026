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

    public Plant register(Plant incoming) {
        if (incoming.getPlantId() == null) {
            List<Long> existing = repo.findDistinctPlantIds();
            long nextId = existing.isEmpty()
                    ? 1L
                    : Collections.max(existing) + 1;
            incoming.setPlantId(nextId);
        }

        if (repo.existsByPlantId(incoming.getPlantId())) {
            return repo.findTopByPlantIdOrderByTimestampDesc(
                    incoming.getPlantId()).orElse(incoming);
        }

        if (incoming.getTimestamp() == null) {
            incoming.setTimestamp(LocalDateTime.now());
        }

        return repo.save(incoming);
    }

    // ═══════════════════════════════════════════════════
    //  SAVING READINGS
    // ═══════════════════════════════════════════════════

    public List<Plant> saveReadings(Long plantId, List<Plant> readings) {
        // Resolve the plant's registered name — fall back gracefully if not
        // yet registered rather than throwing, so ad-hoc readings still land.
        String name = repo.findTopByPlantIdOrderByTimestampDesc(plantId)
                .map(Plant::getName)
                .orElse("Plant " + plantId);

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
     * One Plant object per registered plantId, each being the most
     * recent reading. Powers the overview card grid.
     *
     * Uses findDistinctPlantIds() which queries the plantId column
     * (not the auto-increment PK), so sending multiple readings for
     * the same plant never creates phantom extra plant entries.
     */
    public List<Plant> getAllLatest() {
        List<Long> plantIds = repo.findDistinctPlantIds();
        List<Plant> latest = new ArrayList<>();

        for (Long pid : plantIds) {
            repo.findTopByPlantIdOrderByTimestampDesc(pid)
                    .ifPresent(latest::add);
        }

        latest.sort(Comparator.comparing(Plant::getPlantId));
        return latest;
    }

    /**
     * Latest reading for a single plant, looked up by logical plantId
     * (not the database row PK).
     */
    public Plant getById(Long plantId) {
        return repo.findTopByPlantIdOrderByTimestampDesc(plantId)
                .orElseThrow(() -> new NoSuchElementException(
                        "No plant found with plantId " + plantId));
    }

    // ═══════════════════════════════════════════════════
    //  HISTORICAL DATA (for Chart.js)
    // ═══════════════════════════════════════════════════

    public ReadingJson getReadingsForPlant(Long plantId) {
        return getReadingsForPlant(plantId, 30 * 24); // default: last 30 days
    }

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

    public Map<String, ReadingJson> getHistoricalMap() {
        List<Long> plantIds = repo.findDistinctPlantIds();
        Map<String, ReadingJson> result = new LinkedHashMap<>();

        for (Long pid : plantIds) {
            result.put(pid.toString(), getReadingsForPlant(pid));
        }

        return result;
    }
}