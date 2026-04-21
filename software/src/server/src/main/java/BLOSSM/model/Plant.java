package BLOSSM.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.*;
import java.time.Duration;
import java.time.LocalDateTime;

@Entity
@Table(name = "plant_readings", indexes = {
        @Index(name = "idx_plant_id",        columnList = "plantId"),
        @Index(name = "idx_plant_timestamp", columnList = "plantId, timestamp")
})
public class Plant {

    // ── Persisted fields ────────────────────────────────

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @JsonIgnore
    private Long id;

    @Column(nullable = false)
    private Long plantId;

    @Column(nullable = false)
    private String name;

    private Double temperature;       // deg C
    private Double soilMoisture;      // %
    private Double soilConductivity;  // uS/cm
    private Integer battery;          // mV

    @Column(nullable = false)
    private LocalDateTime timestamp;

    // ── Constructors ────────────────────────────────────

    protected Plant() { }

    public Plant(Long plantId, String name) {
        this.plantId = plantId;
        this.name    = name;
    }

    public Plant(Long plantId, String name,
                 Double temperature, Double soilMoisture,
                 Double soilConductivity, Integer battery,
                 LocalDateTime timestamp) {
        this.plantId          = plantId;
        this.name             = name;
        this.temperature      = temperature;
        this.soilMoisture     = soilMoisture;
        this.soilConductivity = soilConductivity;
        this.battery          = battery;
        this.timestamp        = timestamp;
    }

    // ── Lifecycle ───────────────────────────────────────

    @PrePersist
    protected void onCreate() {
        if (this.timestamp == null) {
            this.timestamp = LocalDateTime.now();
        }
    }

    // ── Computed getters ────────────────────────────────

    public String getStatus() {
        boolean hasCritical = false;
        boolean hasWarning  = false;

        if (temperature != null) {
            if (temperature > 40 || temperature < 2)    hasCritical = true;
            else if (temperature > 35 || temperature < 5) hasWarning = true;
        }
        if (soilMoisture != null) {
            if (soilMoisture < 10 || soilMoisture > 90)   hasCritical = true;
            else if (soilMoisture < 20 || soilMoisture > 80) hasWarning = true;
        }
        if (soilConductivity != null) {
            if (soilConductivity > 3.0)      hasCritical = true;
            else if (soilConductivity > 2.0) hasWarning = true;
        }
        if (battery != null && battery < 3300) {  // below 3.3 V -> warn
            hasWarning = true;
        }

        if (hasCritical) return "critical";
        if (hasWarning)  return "warning";
        return "healthy";
    }

    public String getLastUpdated() {
        if (timestamp == null) return "No data";
        long minutes = Duration.between(timestamp, LocalDateTime.now()).toMinutes();
        if (minutes < 0)  return "Just now";
        if (minutes < 1)  return "Just now";
        if (minutes < 60) return minutes + " min ago";
        long hours = minutes / 60;
        if (hours < 24) return hours + "h ago";
        return (hours / 24) + "d ago";
    }

    // ── Getters & setters ───────────────────────────────

    public Long getId()                          { return id; }
    public void setId(Long id)                   { this.id = id; }

    public Long getPlantId()                     { return plantId; }
    public void setPlantId(Long plantId)         { this.plantId = plantId; }

    public String getName()                      { return name; }
    public void setName(String name)             { this.name = name; }

    public Double getTemperature()               { return temperature; }
    public void setTemperature(Double v)         { this.temperature = v; }

    public Double getSoilMoisture()              { return soilMoisture; }
    public void setSoilMoisture(Double v)        { this.soilMoisture = v; }

    public Double getSoilConductivity()          { return soilConductivity; }
    public void setSoilConductivity(Double v)    { this.soilConductivity = v; }

    public Integer getBattery()                  { return battery; }
    public void setBattery(Integer battery)      { this.battery = battery; }

    public LocalDateTime getTimestamp()          { return timestamp; }
    public void setTimestamp(LocalDateTime ts)   { this.timestamp = ts; }

    @Override
    public String toString() {
        return "Plant{plantId=" + plantId
                + ", name='" + name + '\''
                + ", temp=" + temperature
                + ", moisture=" + soilMoisture
                + ", conductivity=" + soilConductivity
                + ", battery=" + battery + " mV"
                + ", timestamp=" + timestamp + '}';
    }
}