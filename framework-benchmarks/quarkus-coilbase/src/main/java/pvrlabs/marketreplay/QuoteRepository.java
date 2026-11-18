package pvrlabs.marketreplay;

import jakarta.enterprise.context.ApplicationScoped;

import pvrlabs.coilbase.RepositoryContext;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

@ApplicationScoped
class QuoteRepository {
    private static final String COLUMNS =
            "id, fetched_at, cycle, sample_index, market_time, symbol, price";
    private final RepositoryContext jdbc;

    QuoteRepository(RepositoryContext jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(Instant fetchedAt, QuoteBatch batch) {
        jdbc.useTransaction(
                handle -> {
                    for (FixtureQuote quote : batch.quotes()) {
                        jdbc.update(
                                "INSERT INTO quote_samples(fetched_at, cycle, sample_index,"
                                        + " market_time, symbol, price) VALUES"
                                        + " (:at,:cycle,:sample,:time,:symbol,:price)",
                                q ->
                                        q.bind("at", Timestamp.from(fetchedAt))
                                                .bind("cycle", batch.cycle())
                                                .bind("sample", batch.sampleIndex())
                                                .bind("time", batch.marketTime())
                                                .bind("symbol", quote.symbol())
                                                .bind("price", quote.price())
                                                .execute());
                    }
                });
    }

    List<QuoteObservation> latest() {
        return jdbc.query(
                "SELECT "
                        + COLUMNS
                        + " FROM quote_samples WHERE id IN "
                        + "(SELECT MAX(id) FROM quote_samples GROUP BY symbol) ORDER BY symbol",
                q ->
                        q.map(
                                        (rs, ctx) ->
                                                new QuoteObservation(
                                                        rs.getLong("id"),
                                                        rs.getTimestamp("fetched_at").toInstant(),
                                                        rs.getInt("cycle"),
                                                        rs.getInt("sample_index"),
                                                        rs.getString("market_time"),
                                                        rs.getString("symbol"),
                                                        rs.getBigDecimal("price")))
                                .list());
    }

    List<QuoteObservation> history() {
        return jdbc.query(
                "SELECT "
                        + COLUMNS
                        + " FROM (SELECT "
                        + COLUMNS
                        + ", ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY id DESC) AS position "
                        + "FROM quote_samples) recent WHERE position <= 390 ORDER BY id",
                q ->
                        q.map(
                                        (rs, ctx) ->
                                                new QuoteObservation(
                                                        rs.getLong("id"),
                                                        rs.getTimestamp("fetched_at").toInstant(),
                                                        rs.getInt("cycle"),
                                                        rs.getInt("sample_index"),
                                                        rs.getString("market_time"),
                                                        rs.getString("symbol"),
                                                        rs.getBigDecimal("price")))
                                .list());
    }

    long count() {
        return jdbc.query("SELECT COUNT(*) FROM quote_samples", q -> q.mapTo(Long.class).one());
    }

    boolean hasMarketPrices() {
        return jdbc.query(
                        "SELECT COUNT(DISTINCT symbol) FROM quote_samples WHERE symbol IN"
                                + " ('AAPL','GOOG','NVDA')",
                        q -> q.mapTo(Long.class).one())
                == 3;
    }
}
