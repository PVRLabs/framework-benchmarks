package pvrlabs.marketreplay;

import java.math.BigDecimal;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
class PortfolioInitializer implements SmartInitializingSingleton {
    private final PortfolioRepository repository;
    private final TransactionTemplate transactions;
    private final int users;

    PortfolioInitializer(PortfolioRepository repository, TransactionTemplate transactions,
            @Value("${portfolio.seed-users:1000}") int users) {
        this.repository = repository;
        this.transactions = transactions;
        this.users = users;
    }

    @Override
    public void afterSingletonsInstantiated() {
        if (users < 1 || users > 1000000) throw new IllegalArgumentException("seed-users must be 1..1000000");
        transactions.executeWithoutResult(status -> {
            var previous = repository.findSeedUserCount();
            if (previous.isPresent()) {
                if (previous.get() != users) throw new IllegalStateException("Seed count changed; reset the database explicitly");
                return;
            }
            // One initializer per database. The marker and all seeded rows commit together.
            repository.insertSeedMarker(users);
            for (long id = 1; id <= users; id++) {
                repository.insertUser(id, "User " + id);
                int ordinal = 0;
                for (String symbol : java.util.List.of("AAPL", "GOOG", "NVDA")) {
                    BigDecimal quantity = BigDecimal.valueOf(1 + (id * 7 + ordinal++ * 11) % 100);
                    repository.insertHolding(id, symbol, quantity);
                }
            }
        });
    }
}
