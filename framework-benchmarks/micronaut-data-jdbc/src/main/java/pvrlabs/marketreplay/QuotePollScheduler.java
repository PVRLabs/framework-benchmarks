package pvrlabs.marketreplay;

import jakarta.annotation.PreDestroy;
import io.micronaut.runtime.event.annotation.EventListener;
import io.micronaut.runtime.server.event.ServerStartupEvent;
import jakarta.inject.Singleton;

import io.micronaut.context.annotation.Value;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Singleton
class QuotePollScheduler {
    private static final Logger log = LoggerFactory.getLogger(QuotePollScheduler.class);
    private final QuoteSyncService syncService;
    private final boolean enabled;
    private final long interval;
    private final long initialDelay;
    private ScheduledExecutorService executor;

    QuotePollScheduler(
            QuoteSyncService syncService,
            @Value("${market.poll-enabled:true}") boolean enabled,
            @Value("${market.poll-interval-ms:60000}") long interval,
            @Value("${market.poll-initial-delay-ms:0}")
                    long initialDelay) {
        this.enabled = enabled;
        this.syncService = syncService;
        this.interval = interval;
        this.initialDelay = initialDelay;
    }

    @EventListener
    void start(ServerStartupEvent event) {
        if (!enabled) return;
        if (interval <= 0 || initialDelay < 0)
            throw new IllegalArgumentException("invalid poll timing");
        // Match the shared fixed-delay scheduler and shutdown behavior.
        executor =
                Executors.newSingleThreadScheduledExecutor(
                        runnable -> {
                            Thread thread = new Thread(runnable, "market-poll");
                            thread.setDaemon(false);
                            return thread;
                        });
        executor.scheduleWithFixedDelay(this::poll, initialDelay, interval, TimeUnit.MILLISECONDS);
    }

    @PreDestroy
    void stop() {
        if (executor == null) return;
        executor.shutdownNow();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                log.warn("Market quote scheduler did not stop within five seconds");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private void poll() {
        try {
            syncService.pollOnce();
            log.info("Synchronized three market quotes");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            log.info("Market quote poll interrupted");
        } catch (Exception exception) {
            log.warn("Market quote poll failed; the next scheduled poll will retry", exception);
        }
    }
}
