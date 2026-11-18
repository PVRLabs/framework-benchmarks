package pvrlabs.marketreplay;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

class QuotePollScheduler {
    private static final System.Logger log =
            System.getLogger(QuotePollScheduler.class.getName());
    private final QuoteSyncService syncService;
    private final boolean enabled;
    private final long interval;
    private final long initialDelay;
    private ScheduledExecutorService executor;

    QuotePollScheduler(
            QuoteSyncService syncService, boolean enabled, long interval, long initialDelay) {
        // Constructed during route registration, before Jex starts accepting requests.
        if (enabled && (interval <= 0 || initialDelay < 0)) {
            throw new IllegalArgumentException("invalid poll timing");
        }
        this.enabled = enabled;
        this.syncService = syncService;
        this.interval = interval;
        this.initialDelay = initialDelay;
    }

    void start() {
        if (!enabled) return;
        // Framework scheduler APIs are not consistent across Spring, Quarkus, and Micronaut,
        // and many applications use their own executors. Market Replay uses the same JDK
        // scheduled executor in all three ports so scheduling is held constant rather than
        // becoming part of the framework comparison.
        executor =
                Executors.newSingleThreadScheduledExecutor(
                        runnable -> {
                            Thread thread = new Thread(runnable, "market-poll");
                            thread.setDaemon(false);
                            return thread;
                        });
        executor.scheduleWithFixedDelay(this::poll, initialDelay, interval, TimeUnit.MILLISECONDS);
    }

    void stop() {
        if (executor == null) return;
        executor.shutdownNow();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                log.log(System.Logger.Level.WARNING, "Market quote scheduler did not stop within five seconds");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private void poll() {
        try {
            syncService.pollOnce();
            log.log(System.Logger.Level.INFO, "Synchronized three market quotes");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            log.log(System.Logger.Level.INFO, "Market quote poll interrupted");
        } catch (Exception exception) {
            log.log(System.Logger.Level.WARNING, "Market quote poll failed; the next scheduled poll will retry", exception);
        }
    }
}
