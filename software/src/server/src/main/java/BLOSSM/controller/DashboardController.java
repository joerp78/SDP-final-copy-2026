package BLOSSM.controller;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import BLOSSM.service.HubService;
import BLOSSM.service.PlantService;

@Controller
public class DashboardController {

    private final HubService hubService;
    private final PlantService plantService;
    private final ObjectMapper objectMapper;

    public DashboardController(HubService hubService,
                               PlantService plantService,
                               ObjectMapper objectMapper) {
        this.hubService    = hubService;
        this.plantService  = plantService;
        this.objectMapper  = objectMapper;
    }

    @GetMapping("/")
    public String dashboard(Model model) throws JsonProcessingException {

        model.addAttribute("hub", hubService.getLatestReading());
        model.addAttribute("plants", plantService.getAllLatest());

        model.addAttribute("plantDataJson",
                objectMapper.writeValueAsString(
                        plantService.getHistoricalMap()));

        model.addAttribute("hubDataJson",
                objectMapper.writeValueAsString(
                        hubService.getHistorical()));

        return "index";
    }

    @GetMapping("/plants/{id}")
    public String plantDetail(@PathVariable Long id,
                              Model model) throws JsonProcessingException {

        model.addAttribute("plant", plantService.getById(id));

        // ── getReadingsForPlant returns ReadingJson ──
        // ── ObjectMapper serialises it to the JSON shape Chart.js expects ──
        model.addAttribute("readingsJson",
                objectMapper.writeValueAsString(
                        plantService.getReadingsForPlant(id)));

        return "plant";
    }
}