package pvrlabs.marketreplay;

import io.micronaut.data.annotation.Query;
import io.micronaut.data.jdbc.annotation.JdbcRepository;
import io.micronaut.data.model.query.builder.sql.Dialect;
import io.micronaut.data.repository.GenericRepository;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

@JdbcRepository(dialect = Dialect.POSTGRES)
interface QuoteRepository extends GenericRepository<QuoteObservation, Long> {
    String COLUMNS = "id, fetched_at, cycle, sample_index, market_time, symbol, price";

    @Query("""
            INSERT INTO quote_samples(fetched_at, cycle, sample_index, market_time, symbol, price)
            VALUES (:fetchedAt,:cycle,:sampleIndex,:marketTime,:symbol,:price)
            """)
    void insert(Instant fetchedAt, int cycle, int sampleIndex, String marketTime,
                String symbol, BigDecimal price);

    @Query("SELECT " + COLUMNS + " FROM quote_samples WHERE id IN "
            + "(SELECT MAX(id) FROM quote_samples GROUP BY symbol) ORDER BY symbol")
    List<QuoteObservation> latest();

    @Query("SELECT " + COLUMNS + " FROM (SELECT " + COLUMNS
            + ", ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY id DESC) AS position "
            + "FROM quote_samples) recent WHERE position <= 390 ORDER BY id")
    List<QuoteObservation> history();

    @Query("SELECT COUNT(DISTINCT symbol)=3 FROM quote_samples WHERE symbol IN ('AAPL','GOOG','NVDA')")
    boolean hasMarketPrices();
}
