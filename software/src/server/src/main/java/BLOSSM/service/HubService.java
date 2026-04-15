package BLOSSM.service;

import org.springframework.stereotype.Service;
import BLOSSM.model.Hub;
import BLOSSM.model.ReadingJson;
import BLOSSM.repository.HubRepository;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class HubService {

    private final HubRepository repo;

    public HubService(HubRepository repo) {
        this.repo = repo;
    }

    // ═══════════════════════════════════════════════════
    //  SAVING READINGS
    // ═══════════════════════════════════════════════════

    /**
     * Save a batch of hub environment readings.
     * Stamps any missing timestamps with the current time.
     */
    public List<Hub> saveReadings(List<Hub> readings) {
        for (Hub r : readings) {
            if (r.getTimestamp() == null) {
                r.setTimestamp(LocalDateTime.now());
            }
        }
        return repo.saveAll(readings);
    }

    // ═══════════════════════════════════════════════════
    //  LATEST SNAPSHOT
    // ═══════════════════════════════════════════════════

    /**
     * Most recent hub reading.
     * Returns null if no readings exist yet — the template
     * handles this with th:if="${hub != null}".
     */
    public Hub getLatestReading() {
        return repo.findTopByOrderByTimestampDesc()
                .orElse(null);
    }

    // ═══════════════════════════════════════════════════
    //  HISTORICAL DATA (for Chart.js)
    // ═══════════════════════════════════════════════════

    /**
     * Hub history, default last 24 hours.
     */
    public ReadingJson getHistorical() {
        return getHistorical(24);
    }

    /**
     * Hub history within the given hour window.
     *
     * Returns a ReadingJson like:
     * {
     *   "labels":   ["08:00","08:05","08:10"],
     *   "light":    [850.0, 920.0, 870.0],
     *   "humidity": [62.0, 60.5, 61.8]
     * }
     */
    public ReadingJson getHistorical(int hours) {
        LocalDateTime since = LocalDateTime.now().minusHours(hours);

        List<Hub> readings =
                repo.findByTimestampAfterOrderByTimestampAsc(since);

        if (readings.isEmpty()) {
            return ReadingJson.empty();
        }

        return ReadingJson.fromHub(readings);
    }
}