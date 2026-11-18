package pvrlabs.marketreplay;

import pvrlabs.coilbase.RepositoryContext;

import java.math.BigDecimal;

final class PortfolioInitializer {
    static void initialize(RepositoryContext db, int users) {
        if (users < 1 || users > 1000000) {
            throw new IllegalArgumentException("seed-users must be 1..1000000");
        }
        db.useTransaction(
                h -> {
                    db.executeScriptResource("schema-postgres.sql");
                    var prior =
                            db.query(
                                    "SELECT user_count FROM portfolio_seed WHERE id=1",
                                    q -> q.mapTo(Integer.class).findOne());
                    if (prior.isPresent()) {
                        if (prior.get() != users) {
                            throw new IllegalStateException(
                                    "Seed count changed; reset database explicitly");
                        }
                        return;
                    }
                    h.createUpdate("INSERT INTO portfolio_seed VALUES (1, :n)")
                            .bind("n", users)
                            .execute();
                    for (long id = 1; id <= users; id++) {
                        h.createUpdate("INSERT INTO users VALUES (:id,:name)")
                                .bind("id", id)
                                .bind("name", "User " + id)
                                .execute();
                        int ordinal = 0;
                        for (String symbol : java.util.List.of("AAPL", "GOOG", "NVDA")) {
                            h.createUpdate(
                                            "INSERT INTO portfolio_holdings VALUES"
                                                    + " (:id,:symbol,:quantity)")
                                    .bind("id", id)
                                    .bind("symbol", symbol)
                                    .bind(
                                            "quantity",
                                            BigDecimal.valueOf(1 + (id * 7 + ordinal++ * 11) % 100))
                                    .execute();
                        }
                    }
                });
    }
}
