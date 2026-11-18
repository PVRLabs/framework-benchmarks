package pvrlabs.marketreplay;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReadinessController {
    private final ReadinessService service;

    ReadinessController(ReadinessService service) {
        this.service = service;
    }

    @GetMapping("/readyz")
    ResponseEntity<Map<String, String>> ready() {
        if (service.isReady()) {
            return ResponseEntity.ok(Map.of("status", "UP"));
        }
        return ResponseEntity.status(503).body(Map.of("status", "DOWN"));
    }
}
