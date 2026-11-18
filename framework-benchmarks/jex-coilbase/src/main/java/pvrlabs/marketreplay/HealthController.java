package pvrlabs.marketreplay;

import io.avaje.http.api.Controller;
import io.avaje.http.api.Get;
import io.avaje.jex.http.Context;

import org.jdbi.v3.core.Jdbi;

import pvrlabs.coilbase.monitoring.DatabaseHealth;

import java.util.Map;

@Controller
public final class HealthController {
    private final ReadinessService readiness;
    private final Jdbi database;

    public HealthController(ReadinessService readiness, Jdbi database) {
        this.readiness = readiness;
        this.database = database;
    }

    @Get("/readyz")
    public Map<String, String> ready(Context ctx) {
        boolean up = readiness.isReady();
        ctx.status(up ? 200 : 503);
        return Map.of("status", up ? "UP" : "DOWN");
    }

    // Explicit operational probe, separate from opt-in cached monitoring.
    @Get("/healthz")
    public Map<String, String> health(Context ctx) {
        boolean up = DatabaseHealth.check(database, 2).healthy();
        ctx.status(up ? 200 : 503);
        return Map.of("status", up ? "UP" : "DOWN");
    }
}
