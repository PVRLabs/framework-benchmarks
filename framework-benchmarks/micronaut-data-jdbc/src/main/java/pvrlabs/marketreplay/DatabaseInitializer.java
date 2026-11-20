package pvrlabs.marketreplay;

import io.micronaut.context.annotation.Context;
import io.micronaut.context.annotation.Value;
import io.micronaut.transaction.TransactionOperations;
import jakarta.annotation.PostConstruct;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.util.List;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.SQLException;

@Context
class DatabaseInitializer {
    private final TransactionOperations<Connection> transactions;
    private final PortfolioRepository portfolios;
    private final int users;

    DatabaseInitializer(TransactionOperations<Connection> transactions, PortfolioRepository portfolios,
                        @Value("${portfolio.seed-users:1000}") int users) {
        this.transactions = transactions;
        this.portfolios = portfolios;
        this.users = users;
    }

    @PostConstruct
    void initialize() {
        if (users < 1 || users > 1_000_000) {
            throw new IllegalArgumentException("seed-users must be 1..1000000");
        }
        String schema;
        try (var input = getClass().getResourceAsStream("/schema-postgres.sql")) {
            if (input == null) {
                throw new IllegalStateException("Missing PostgreSQL schema");
            }
            schema = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }

        transactions.executeWrite(status -> {
            var connection = status.getConnection();
            try (var statement = connection.createStatement()) {
                statement.execute(schema);
                var previous = portfolios.findSeedUserCount();
                if (previous.isPresent()) {
                    if (previous.get() != users) {
                        throw new IllegalStateException("Seed count changed; reset database explicitly");
                    }
                    return null;
                }
                portfolios.insertSeedMarker(users);
                for (long id = 1; id <= users; id++) {
                    portfolios.insertUser(id, "User " + id);
                    int ordinal = 0;
                    for (String symbol : List.of("AAPL", "GOOG", "NVDA")) {
                        portfolios.insertHolding(id, symbol,
                                BigDecimal.valueOf(1 + (id * 7 + ordinal++ * 11) % 100));
                    }
                }
                return null;
            } catch (SQLException e) {
                throw new IllegalStateException("Could not initialize PostgreSQL schema and seed", e);
            }
        });
    }
}
