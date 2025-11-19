package rfid.service;

import rfid.model.RFIDEvent;
import org.springframework.stereotype.Service;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

@Service
public class RFIDEventService {
    private final Map<Long, RFIDEvent> events = new LinkedHashMap<>();
    private final AtomicLong idGen = new AtomicLong(1);

    public List<RFIDEvent> saveAll(List<RFIDEvent> incomingEvents) {
        List<RFIDEvent> saved = new ArrayList<>();

        for (RFIDEvent event : incomingEvents) {
            Long id = idGen.getAndIncrement();
            RFIDEvent withId = new RFIDEvent(id, event.timestamp(), event.eventType(),
                    event.epc(), event.userMemory(), event.rssi(), event.antennaId());
            events.put(id, withId);
            saved.add(withId);
        }

        return saved;
    }

    public List<RFIDEvent> findAll() {
        return new ArrayList<>(events.values());
    }
}