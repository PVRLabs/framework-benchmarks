package pvrlabs.marketreplay;

import io.micronaut.data.annotation.GeneratedValue;
import io.micronaut.data.annotation.Id;
import io.micronaut.data.annotation.MappedEntity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

record QuoteBatch(int cycle, String marketTime, int sampleIndex, List<FixtureQuote> quotes) {}

record FixtureQuote(String symbol, BigDecimal price) {}

@MappedEntity("quote_samples")
record QuoteObservation(
        @Id @GeneratedValue long id,
        Instant fetchedAt,
        int cycle,
        int sampleIndex,
        String marketTime,
        String symbol,
        BigDecimal price) {}
