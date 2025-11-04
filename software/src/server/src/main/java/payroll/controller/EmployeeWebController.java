package payroll.controller;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import payroll.model.Employee;
import payroll.service.EmployeeService;

@Controller
public class EmployeeWebController {

    private final EmployeeService svc;

    public EmployeeWebController(EmployeeService svc) {
        this.svc = svc;
    }

    // Home page — list employees and show create form
    @GetMapping("/")
    public String index(Model model) {
        model.addAttribute("employees", svc.findAll());
        model.addAttribute("employeeForm", new Employee(null, "", ""));
        return "index"; // resolves to src/main/resources/templates/index.html
    }

    // Create employee (POST from form)
    @PostMapping("/employees")
    public String create(@ModelAttribute("employeeForm") Employee form) {
        svc.save(new Employee(null, form.name(), form.role()));
        return "redirect:/";
    }

    // Show single employee page (optional)
    @GetMapping("/employees/{id}")
    public String show(@PathVariable Long id, Model model) {
        return svc.findById(id)
                .map(emp -> {
                    model.addAttribute("employee", emp);
                    return "employee"; // src/main/resources/templates/employee.html
                })
                .orElse("redirect:/");
    }

    // Delete (form submits POST to this endpoint)
    @PostMapping("/employees/{id}/delete")
    public String delete(@PathVariable Long id) {
        svc.delete(id);
        return "redirect:/";
    }
}
