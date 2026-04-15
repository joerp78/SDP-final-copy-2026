package BLOSSM.service;

import BLOSSM.model.RFIDReading;
import org.springframework.stereotype.Service;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

@Service
public class WebService {
    private final Map<Long, RFIDReading> events = new LinkedHashMap<>();
    private final AtomicLong idGen = new AtomicLong(1);

    public List<RFIDReading> saveAll(List<RFIDReading> incomingEvents) {
        List<RFIDReading> saved = new ArrayList<>();

        for (RFIDReading event : incomingEvents) {
            Long id = idGen.getAndIncrement();
            RFIDReading withId = new RFIDReading(id, event.timestamp(), event.eventType(),
                    event.epc(), event.userMemory(), event.rssi(), event.antennaId());
            events.put(id, withId);
            saved.add(withId);
        }

        return saved;
    }

    public List<RFIDReading> findAll() {
        return new ArrayList<>(events.values());
    }
}