package pvrlabs.marketreplay;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
class QuoteRepository {
    private static final String COLUMNS = "id, fetched_at, cycle, sample_index, market_time, symbol, price";
    private static final RowMapper<QuoteObservation> QUOTE_MAPPER =
            new QuoteObservationRowMapper();
    private final JdbcClient jdbc;

    QuoteRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void insert(Instant fetchedAt, QuoteBatch batch) {
        for (FixtureQuote quote : batch.quotes()) {
            jdbc.sql("INSERT INTO quote_samples(fetched_at, cycle, sample_index, market_time, symbol, price) "
                            + "VALUES (:fetchedAt, :cycle, :sampleIndex, :marketTime, :symbol, :price)")
                    .param("fetchedAt", Timestamp.from(fetchedAt))
                    .param("cycle", batch.cycle())
                    .param("sampleIndex", batch.sampleIndex())
                    .param("marketTime", batch.marketTime())
                    .param("symbol", quote.symbol())
                    .param("price", quote.price())
                    .update();
        }
    }

    List<QuoteObservation> latest() {
        return jdbc.sql("SELECT " + COLUMNS + " FROM quote_samples WHERE id IN "
                        + "(SELECT MAX(id) FROM quote_samples GROUP BY symbol) ORDER BY symbol")
                .query(QUOTE_MAPPER).list();
    }

    List<QuoteObservation> history() {
        return jdbc.sql("SELECT " + COLUMNS + " FROM (SELECT " + COLUMNS
                        + ", ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY id DESC) AS position "
                        + "FROM quote_samples) recent WHERE position <= 390 ORDER BY id")
                .query(QUOTE_MAPPER)
                .list();
    }

    long count() {
        return jdbc.sql("SELECT COUNT(*) FROM quote_samples").query(Long.class).single();
    }

    boolean hasMarketPrices() {
        return jdbc.sql("SELECT COUNT(DISTINCT symbol) FROM quote_samples WHERE symbol IN ('AAPL','GOOG','NVDA')")
                .query(Long.class).single() == 3;
    }
}
