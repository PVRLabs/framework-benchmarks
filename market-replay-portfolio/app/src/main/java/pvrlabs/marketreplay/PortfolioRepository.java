package pvrlabs.marketreplay;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
class PortfolioRepository {
    private static final RowMapper<PricedHolding> HOLDING_MAPPER = new PortfolioHoldingRowMapper();
    private final JdbcClient jdbc;

    PortfolioRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    boolean userExists(long userId) {
        return jdbc.sql("SELECT id FROM users WHERE id=?")
                .param(userId).query(Long.class).optional().isPresent();
    }

    // Caller must hold a transaction until the corresponding edit commits.
    boolean lockUser(long userId) {
        return jdbc.sql("SELECT id FROM users WHERE id=? FOR UPDATE")
                .param(userId).query(Long.class).optional().isPresent();
    }

    List<PricedHolding> findHoldingsWithLatestPrices(long userId) {
        // One statement gives all holdings the same committed price snapshot.
        return jdbc.sql("""
                SELECT h.symbol, h.quantity, q.price FROM portfolio_holdings h
                LEFT JOIN quote_samples q ON q.id=(SELECT MAX(s.id) FROM quote_samples s WHERE s.symbol=h.symbol)
                WHERE h.user_id=? ORDER BY h.symbol
                """).param(userId).query(HOLDING_MAPPER).list();
    }

    // Called after lockUser, so checking an absent holding and inserting it is safe.
    void saveHolding(long userId, String symbol, BigDecimal quantity) {
        int updated = jdbc.sql("UPDATE portfolio_holdings SET quantity=? WHERE user_id=? AND symbol=?")
                .params(quantity, userId, symbol).update();
        // Some JDBC settings report changed rows rather than matched rows.
        if (updated == 0 && !holdingExists(userId, symbol)) {
            insertHolding(userId, symbol, quantity);
        }
    }

    void deleteHolding(long userId, String symbol) {
        jdbc.sql("DELETE FROM portfolio_holdings WHERE user_id=? AND symbol=?")
                .params(userId, symbol).update();
    }

    private boolean holdingExists(long userId, String symbol) {
        return jdbc.sql("SELECT symbol FROM portfolio_holdings WHERE user_id=? AND symbol=?")
                .params(userId, symbol).query(String.class).optional().isPresent();
    }

    void insertHolding(long userId, String symbol, BigDecimal quantity) {
        jdbc.sql("INSERT INTO portfolio_holdings(user_id,symbol,quantity) VALUES (?,?,?)")
                .params(userId, symbol, quantity).update();
    }

    Optional<Integer> findSeedUserCount() {
        return jdbc.sql("SELECT user_count FROM portfolio_seed WHERE id=1").query(Integer.class).optional();
    }

    void insertSeedMarker(int userCount) {
        jdbc.sql("INSERT INTO portfolio_seed(id,user_count) VALUES (1,?)").param(userCount).update();
    }

    void insertUser(long userId, String name) {
        jdbc.sql("INSERT INTO users(id,name) VALUES (?,?)").params(userId, name).update();
    }
}
