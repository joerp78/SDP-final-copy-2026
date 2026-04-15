package BLOSSM.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import BLOSSM.model.Hub;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface HubRepository extends JpaRepository<BLOSSM.model.Hub, Long> {

    /**
     * Most recent hub reading.
     *
     *   SELECT * FROM hub_readings
     *   ORDER BY timestamp DESC
     *   LIMIT 1
     */
    Optional<Hub> findTopByOrderByTimestampDesc();

    /**
     * All hub readings after a cutoff, oldest → newest.
     *
     *   SELECT * FROM hub_readings
     *   WHERE timestamp >= ?
     *   ORDER BY timestamp ASC
     */
    List<Hub> findByTimestampAfterOrderByTimestampAsc(LocalDateTime since);
}