package rfid.controller;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import rfid.service.RFIDEventService;

@Controller
public class RFIDEventWebController {

    private final RFIDEventService service;

    public RFIDEventWebController(RFIDEventService service) {
        this.service = service;
    }

    @GetMapping("/")
    public String showEvents(Model model) {
        model.addAttribute("events", service.findAll());
        return "index";  // looks for templates/rfid-events.html
    }
}