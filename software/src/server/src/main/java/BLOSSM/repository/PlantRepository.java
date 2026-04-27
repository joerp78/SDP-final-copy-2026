package BLOSSM.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;
import BLOSSM.model.Plant;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface PlantRepository extends JpaRepository<Plant, Long> {

    /**
     * Get every distinct plantId that has been registered.
     *
     *   SELECT DISTINCT plant_id FROM plant_readings
     */
    @Query("SELECT DISTINCT p.plantId FROM Plant p")
    List<Long> findDistinctPlantIds();

    /**
     * Latest single row for a given plantId (most recent timestamp).
     * Used for the overview cards and the detail page header.
     *
     *   SELECT * FROM plant_readings
     *   WHERE plant_id = ?
     *   ORDER BY timestamp DESC
     *   LIMIT 1
     */
    Optional<Plant> findTopByPlantIdOrderByTimestampDesc(Long plantId);

    /**
     * All readings for a plant after a cutoff time, sorted oldest → newest.
     * Used to build the historical chart data.
     *
     *   SELECT * FROM plant_readings
     *   WHERE plant_id = ?
     *     AND timestamp >= ?
     *   ORDER BY timestamp ASC
     */
    List<Plant> findByPlantIdAndTimestampAfterOrderByTimestampAsc(
            Long plantId, LocalDateTime since);

    /**
     * Latest reading for a plant that actually has sensor data (excludes
     * registration rows which have null temperature).
     *
     *   SELECT * FROM plant_readings
     *   WHERE plant_id = ?
     *     AND temperature IS NOT NULL
     *   ORDER BY timestamp DESC
     *   LIMIT 1
     */
    Optional<Plant> findTopByPlantIdAndTemperatureIsNotNullOrderByTimestampDesc(Long plantId);

    /**
     * Check if a plant with this logical ID has already been registered.
     */
    boolean existsByPlantId(Long plantId);
}