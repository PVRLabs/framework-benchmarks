package pvrlabs.marketreplay;

import io.avaje.jex.Jex;

import org.jdbi.v3.core.Jdbi;

import pvrlabs.coilbase.jex.CoilBaseJexApplication;

import java.net.URI;

import javax.sql.DataSource;

public final class PortfolioApplication extends CoilBaseJexApplication {
    private QuotePollScheduler scheduler;
    private Jdbi healthDatabase;

    static String env(String key, String fallback) {
        return System.getenv().getOrDefault(key, fallback);
    }

    @Override
    protected DataSource createPrimaryDataSource() {
        var config = new com.zaxxer.hikari.HikariConfig();
        config.setJdbcUrl(env("MARKET_DB_URL", "jdbc:postgresql://127.0.0.1:15432/fb_baseline"));
        config.setUsername(env("MARKET_DB_USER", "fb_baseline"));
        config.setPassword(env("MARKET_DB_PASSWORD", "fb_baseline"));
        config.setMaximumPoolSize(4);
        config.setTransactionIsolation("TRANSACTION_READ_COMMITTED");
        var pool = new com.zaxxer.hikari.HikariDataSource(config);
        healthDatabase = Jdbi.create(pool);
        return pool;
    }

    @Override
    protected void configureErrorHandling() {
        mapError(InvalidHoldingException.class, 400, "invalid_holding");
        mapError(UserNotFoundException.class, 404, "user_not_found");
        mapError(MarketPricesUnavailableException.class, 503, "market_prices_unavailable");
    }

    @Override
    protected void registerRoutes(Jex jex) {
        PortfolioInitializer.initialize(
                db(), Integer.parseInt(env("PORTFOLIO_SEED_USERS", "1000")));
        var quotes = new QuoteRepository(db());
        var portfolios = new PortfolioRepository(db());
        var readiness = new ReadinessService(portfolios, quotes);
        jex.routing(
                new PortfolioController$Route(
                        new PortfolioController(new PortfolioService(portfolios, db()), quotes)));
        jex.routing(new HealthController$Route(new HealthController(readiness, healthDatabase)));
        scheduler =
                new QuotePollScheduler(
                        new QuoteSyncService(
                                new QuoteClient(
                                        URI.create(
                                                env(
                                                        "MARKET_FIXTURE_URL",
                                                        "http://127.0.0.1:8090/quotes")),
                                        objectMapper()),
                                quotes),
                        Boolean.parseBoolean(env("MARKET_POLL_ENABLED", "true")),
                        Long.parseLong(env("MARKET_POLL_INTERVAL_MS", "60000")),
                        Long.parseLong(env("MARKET_POLL_INITIAL_DELAY_MS", "0")));
        jex.lifecycle().onShutdown(scheduler::stop);
    }

    public static void main(String[] args) {
        var app = new PortfolioApplication();
        try {
            app.start(Integer.parseInt(env("SERVER_PORT", "8080")));
            app.scheduler.start();
        } catch (RuntimeException | Error e) {
            if (app.scheduler != null) app.scheduler.stop();
            throw e;
        }
    }
}
