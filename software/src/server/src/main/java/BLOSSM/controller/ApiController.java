package BLOSSM.controller;

import org.springframework.web.bind.annotation.*;
import BLOSSM.model.Hub;
import BLOSSM.model.Plant;
import BLOSSM.model.ReadingJson;
import BLOSSM.service.HubService;
import BLOSSM.service.PlantService;

import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.*;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*")
public class ApiController {

    private final PlantService plantService;
    private final HubService hubService;

    public ApiController(PlantService plantService, HubService hubService) {
        this.plantService = plantService;
        this.hubService   = hubService;
    }

    // ── Plants ──────────────────────────────────────────

    @GetMapping("/plants")
    public List<Plant> getAllPlants() {
        return plantService.getAllLatest();
    }

    @PostMapping("/plants")
    public Map<String, Object> registerPlant(@RequestBody Plant plant) {
        Plant saved = plantService.register(plant);
        return Map.of(
                "success", true,
                "id",      saved.getPlantId(),
                "name",    saved.getName()
        );
    }

    @GetMapping("/plants/{id}")
    public Plant getPlant(@PathVariable Long id) {
        return plantService.getById(id);
    }

    @PostMapping("/plants/{id}/readings")
    public Map<String, Object> postPlantReadings(
            @PathVariable Long id,
            @RequestBody List<Plant> readings) {

        List<Plant> saved = plantService.saveReadings(id, readings);
        return Map.of(
                "success", true,
                "plantId", id,
                "count",   saved.size()
        );
    }

    @GetMapping("/plants/{id}/readings")
    public ReadingJson getPlantReadings(
            @PathVariable Long id,
            @RequestParam(defaultValue = "24") int hours) {

        return plantService.getReadingsForPlant(id, hours);
    }

    // ── Hub ─────────────────────────────────────────────

    @PostMapping("/hub/readings")
    public Map<String, Object> postHubReadings(
            @RequestBody List<Hub> readings) {

        List<Hub> saved = hubService.saveReadings(readings);
        return Map.of(
                "success", true,
                "count",   saved.size()
        );
    }

    @GetMapping("/hub/latest")
    public Hub getHubLatest() {
        return hubService.getLatestReading();
    }

    @GetMapping("/hub/readings")
    public ReadingJson getHubReadings(
            @RequestParam(defaultValue = "24") int hours) {

        return hubService.getHistorical(hours);
    }

    // ── Health ──────────────────────────────────────────

    @GetMapping("/test")
    public Map<String, Object> test() {
        return Map.of(
                "status",    "ok",
                "message",   "BLOSSM server is running",
                "timestamp", LocalDateTime.now().toString()
        );
    }
}