package pvrlabs.marketreplay;

import pvrlabs.coilbase.RepositoryContext;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

class PortfolioRepository {
    private final RepositoryContext jdbc;

    PortfolioRepository(RepositoryContext jdbc) {
        this.jdbc = jdbc;
    }

    boolean userExists(long userId) {
        return jdbc.query(
                        "SELECT id FROM users WHERE id=?",
                        q -> q.bind(0, userId).mapTo(Long.class).findOne())
                .isPresent();
    }

    // Caller must hold a transaction until the corresponding edit commits.
    boolean lockUser(long userId) {
        return jdbc.query(
                        "SELECT id FROM users WHERE id=? FOR UPDATE",
                        q -> q.bind(0, userId).mapTo(Long.class).findOne())
                .isPresent();
    }

    List<PricedHolding> findHoldingsWithLatestPrices(long userId) {
        // One statement gives all holdings the same committed price snapshot.
        return jdbc.query(
                """
                SELECT h.symbol, h.quantity, q.price FROM portfolio_holdings h
                LEFT JOIN quote_samples q ON q.id=(SELECT MAX(s.id) FROM quote_samples s WHERE s.symbol=h.symbol)
                WHERE h.user_id=? ORDER BY h.symbol
                """,
                q ->
                        q.bind(0, userId)
                                .map(
                                        (rs, ctx) ->
                                                new PricedHolding(
                                                        rs.getString("symbol"),
                                                        rs.getBigDecimal("quantity"),
                                                        rs.getBigDecimal("price")))
                                .list());
    }

    // Called after lockUser, so checking an absent holding and inserting it is safe.
    void saveHolding(long userId, String symbol, BigDecimal quantity) {
        int updated =
                jdbc.update(
                        "UPDATE portfolio_holdings SET quantity=? WHERE user_id=? AND symbol=?",
                        q -> q.bind(0, quantity).bind(1, userId).bind(2, symbol).execute());
        // Some JDBC settings report changed rows rather than matched rows.
        if (updated == 0 && !holdingExists(userId, symbol)) {
            insertHolding(userId, symbol, quantity);
        }
    }

    void deleteHolding(long userId, String symbol) {
        jdbc.update(
                "DELETE FROM portfolio_holdings WHERE user_id=? AND symbol=?",
                q -> q.bind(0, userId).bind(1, symbol).execute());
    }

    private boolean holdingExists(long userId, String symbol) {
        return jdbc.query(
                        "SELECT symbol FROM portfolio_holdings WHERE user_id=? AND symbol=?",
                        q -> q.bind(0, userId).bind(1, symbol).mapTo(String.class).findOne())
                .isPresent();
    }

    void insertHolding(long userId, String symbol, BigDecimal quantity) {
        jdbc.update(
                "INSERT INTO portfolio_holdings(user_id,symbol,quantity) VALUES (?,?,?)",
                q -> q.bind(0, userId).bind(1, symbol).bind(2, quantity).execute());
    }

    Optional<Integer> findSeedUserCount() {
        return jdbc.query(
                "SELECT user_count FROM portfolio_seed WHERE id=1",
                q -> q.mapTo(Integer.class).findOne());
    }

    void insertSeedMarker(int userCount) {
        jdbc.update(
                "INSERT INTO portfolio_seed(id,user_count) VALUES (1,?)",
                q -> q.bind(0, userCount).execute());
    }

    void insertUser(long userId, String name) {
        jdbc.update(
                "INSERT INTO users(id,name) VALUES (?,?)",
                q -> q.bind(0, userId).bind(1, name).execute());
    }
}
