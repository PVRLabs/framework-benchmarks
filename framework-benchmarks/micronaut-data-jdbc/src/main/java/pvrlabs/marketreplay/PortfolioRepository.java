package pvrlabs.marketreplay;

import io.micronaut.data.annotation.Id;
import io.micronaut.data.annotation.MappedEntity;
import io.micronaut.data.annotation.Query;
import io.micronaut.data.jdbc.annotation.JdbcRepository;
import io.micronaut.data.model.query.builder.sql.Dialect;
import io.micronaut.data.repository.GenericRepository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

@MappedEntity("users")
record PortfolioUser(@Id long id, String name) {}

@JdbcRepository(dialect = Dialect.POSTGRES)
interface PortfolioRepository extends GenericRepository<PortfolioUser, Long> {
    boolean existsById(long id);

    @Query("SELECT id FROM users WHERE id=:userId FOR UPDATE")
    Optional<Long> lockUser(long userId);

    // One statement gives all holdings the same committed price snapshot.
    @Query("""
            SELECT h.symbol, h.quantity, q.price FROM portfolio_holdings h
            LEFT JOIN quote_samples q ON q.id=(SELECT MAX(s.id) FROM quote_samples s WHERE s.symbol=h.symbol)
            WHERE h.user_id=:userId ORDER BY h.symbol
            """)
    List<PricedHolding> findHoldingsWithLatestPrices(long userId);

    @Query("""
            INSERT INTO portfolio_holdings(user_id,symbol,quantity) VALUES (:userId,:symbol,:quantity)
            ON CONFLICT (user_id,symbol) DO UPDATE SET quantity=excluded.quantity
            """)
    void saveHolding(long userId, String symbol, BigDecimal quantity);

    @Query("DELETE FROM portfolio_holdings WHERE user_id=:userId AND symbol=:symbol")
    void deleteHolding(long userId, String symbol);

    @Query("SELECT user_count FROM portfolio_seed WHERE id=1")
    Optional<Integer> findSeedUserCount();

    @Query("INSERT INTO portfolio_seed(id,user_count) VALUES (1,:users)")
    void insertSeedMarker(int users);

    @Query("INSERT INTO users(id,name) VALUES (:id,:name)")
    void insertUser(long id, String name);

    @Query("INSERT INTO portfolio_holdings(user_id,symbol,quantity) VALUES (:userId,:symbol,:quantity)")
    void insertHolding(long userId, String symbol, BigDecimal quantity);

    @Query("SELECT 1")
    int databasePing();
}
