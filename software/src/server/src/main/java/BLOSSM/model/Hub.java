package BLOSSM.model;

import jakarta.persistence.*;
import java.time.Duration;
import java.time.LocalDateTime;

@Entity
@Table(name = "hub_readings", indexes = {
        @Index(name = "idx_hub_timestamp", columnList = "timestamp")
})
public class Hub {

    // ── Persisted fields ────────────────────────────────

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Double light;        // brightness % (0.0 - 100.0)
    private Double humidity;     // %
    private Double temperature;  // deg C

    @Column(nullable = false)
    private LocalDateTime timestamp;

    // ── Constructors ────────────────────────────────────

    protected Hub() { }

    public Hub(Double light, Double humidity, Double temperature, LocalDateTime timestamp) {
        this.light       = light;
        this.humidity    = humidity;
        this.temperature = temperature;
        this.timestamp   = timestamp;
    }

    // ── Lifecycle callback ──────────────────────────────

    @PrePersist
    protected void onCreate() {
        if (this.timestamp == null) {
            this.timestamp = LocalDateTime.now();
        }
    }

    // ── Computed getter ─────────────────────────────────

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

    // ── Standard getters & setters ──────────────────────

    public Long getId()                              { return id; }
    public void setId(Long id)                       { this.id = id; }

    public Double getLight()                         { return light; }
    public void setLight(Double light)               { this.light = light; }

    public Double getHumidity()                      { return humidity; }
    public void setHumidity(Double humidity)         { this.humidity = humidity; }

    public Double getTemperature()                   { return temperature; }
    public void setTemperature(Double temperature)   { this.temperature = temperature; }

    public LocalDateTime getTimestamp()                         { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp)           { this.timestamp = timestamp; }

    @Override
    public String toString() {
        return "Hub{id=" + id
                + ", light=" + light
                + ", humidity=" + humidity
                + ", temperature=" + temperature
                + ", timestamp=" + timestamp + '}';
    }
}