package rfid.controller;

import org.springframework.web.bind.annotation.*;
import rfid.model.RFIDEvent;
import rfid.service.RFIDEventService;
import java.util.*;
import java.time.LocalTime;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*")  // Allow cross-origin for testing
public class RFIDEventApiController {

    private final RFIDEventService service;

    public RFIDEventApiController(RFIDEventService service) {
        this.service = service;
    }

    @PostMapping("/events")
    public Map<String, Object> createEvents(@RequestBody List<RFIDEvent> events) {
        System.out.println("========================================");
        System.out.println("POST /api/events - Received request");
        System.out.println("Number of events: " + events.size());
        System.out.println("Events: " + events);
        System.out.println("========================================");

        List<RFIDEvent> saved = service.saveAll(events);
        List<Long> ids = saved.stream().map(RFIDEvent::id).toList();

        Map<String, Object> response = Map.of("success", true, "count", ids.size(), "ids", ids);
        System.out.println(LocalTime.now() + ": Sending response: " + response);

        return response;
    }

    @GetMapping("/events")
    public List<RFIDEvent> getAllEvents() {
        System.out.println("GET /api/events - Returning " + service.findAll().size() + " events");
        return service.findAll();
    }

    // Simple test endpoint
    @GetMapping("/test")
    public Map<String, String> test() {
        System.out.println("GET /api/test called");
        return Map.of("status", "ok", "message", "Server is working");
    }
}