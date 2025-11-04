package payroll.service;

import payroll.model.Employee;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

@Service
public class EmployeeService {
    private final Map<Long, Employee> store = new LinkedHashMap<>();
    private final AtomicLong idGen = new AtomicLong(1);

    public EmployeeService() {
        // optional seed
        save(new Employee(null, "Frodo Baggins", "ring-bearer"));
    }

    public List<Employee> findAll() {
        return new ArrayList<>(store.values());
    }

    public Optional<Employee> findById(Long id) {
        return Optional.ofNullable(store.get(id));
    }

    public Employee save(Employee e) {
        Long id = e.id() == null ? idGen.getAndIncrement() : e.id();
        Employee saved = new Employee(id, e.name(), e.role());
        store.put(id, saved);
        return saved;
    }

    public boolean delete(Long id) {
        return store.remove(id) != null;
    }
}
