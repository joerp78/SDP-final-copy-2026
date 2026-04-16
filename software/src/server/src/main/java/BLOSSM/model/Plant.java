package BLOSSM.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.*;
import java.time.Duration;
import java.time.LocalDateTime;

@Entity
@Table(name = "plant_readings", indexes = {
        @Index(name = "idx_plant_id", columnList = "plantId"),
        @Index(name = "idx_plant_timestamp", columnList = "plantId, timestamp")
})
public class Plant {

    // ── Persisted fields ────────────────────────────────

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @JsonIgnore                       // hide the internal row PK from JSON
    private Long id;

    @Column(nullable = false)
    private Long plantId;             // logical plant identifier — used in URLs

    @Column(nullable = false)
    private String name;              // "Basil", "Tomato", etc.

    private Double temperature;       // °C
    private Double soilMoisture;      // %
    private Double soilConductivity;  // µS/cm

    @Column(nullable = false)
    private LocalDateTime timestamp;

    // ── Constructors ────────────────────────────────────

    protected Plant() { }   // required by JPA

    /** Used when registering a brand-new plant (POST /api/plants) */
    public Plant(Long plantId, String name) {
        this.plantId = plantId;
        this.name    = name;
    }

    /** Used when saving a sensor reading */
    public Plant(Long plantId, String name,
                 Double temperature, Double soilMoisture,
                 Double soilConductivity, LocalDateTime timestamp) {
        this.plantId           = plantId;
        this.name              = name;
        this.temperature       = temperature;
        this.soilMoisture      = soilMoisture;
        this.soilConductivity  = soilConductivity;
        this.timestamp         = timestamp;
    }

    // ── Lifecycle callback ──────────────────────────────

    @PrePersist
    protected void onCreate() {
        if (this.timestamp == null) {
            this.timestamp = LocalDateTime.now();
        }
    }

    // ── Computed getters (NOT stored in DB) ─────────────
    //    JPA uses field-based access (annotations are on fields),
    //    so extra getters are invisible to Hibernate but visible
    //    to Thymeleaf (${plant.status}) and Jackson (JSON).

    /**
     * Derives a health status from the latest sensor values.
     * Adjust these thresholds to match your plants' needs.
     */
    public String getStatus() {
        boolean hasCritical = false;
        boolean hasWarning  = false;

        if (temperature != null) {
            if (temperature > 40 || temperature < 2)  hasCritical = true;
            else if (temperature > 35 || temperature < 5) hasWarning = true;
        }
        if (soilMoisture != null) {
            if (soilMoisture < 10 || soilMoisture > 90) hasCritical = true;
            else if (soilMoisture < 20 || soilMoisture > 80) hasWarning = true;
        }
        if (soilConductivity != null) {
            if (soilConductivity > 3.0) hasCritical = true;
            else if (soilConductivity > 2.0) hasWarning = true;
        }

        if (hasCritical) return "critical";
        if (hasWarning)  return "warning";
        return "healthy";
    }

    /**
     * Human-friendly relative time string for the template.
     */
    public String getLastUpdated() {
        if (timestamp == null) return "No data";

        long minutes = Duration.between(timestamp, LocalDateTime.now()).toMinutes();
        if (minutes < 0)  return "Just now";        // clock skew guard
        if (minutes < 1)  return "Just now";
        if (minutes < 60) return minutes + " min ago";

        long hours = minutes / 60;
        if (hours < 24) return hours + "h ago";

        long days = hours / 24;
        return days + "d ago";
    }

    // ── Standard getters & setters ──────────────────────

    public Long getId()                    { return id; }
    public void setId(Long id)             { this.id = id; }

    public Long getPlantId()               { return plantId; }
    public void setPlantId(Long plantId)   { this.plantId = plantId; }

    public String getName()                { return name; }
    public void setName(String name)       { this.name = name; }

    public Double getTemperature()                   { return temperature; }
    public void setTemperature(Double temperature)   { this.temperature = temperature; }

    public Double getSoilMoisture()                  { return soilMoisture; }
    public void setSoilMoisture(Double soilMoisture) { this.soilMoisture = soilMoisture; }

    public Double getSoilConductivity()                        { return soilConductivity; }
    public void setSoilConductivity(Double soilConductivity)   { this.soilConductivity = soilConductivity; }

    public LocalDateTime getTimestamp()                  { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp)     { this.timestamp = timestamp; }

    @Override
    public String toString() {
        return "Plant{plantId=" + plantId
                + ", name='" + name + '\''
                + ", temp=" + temperature
                + ", moisture=" + soilMoisture
                + ", conductivity=" + soilConductivity
                + ", timestamp=" + timestamp + '}';
    }
}