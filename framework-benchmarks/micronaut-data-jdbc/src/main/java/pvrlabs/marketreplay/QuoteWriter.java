package pvrlabs.marketreplay;

import jakarta.inject.Singleton;
import jakarta.transaction.Transactional;

import java.time.Instant;

@Singleton
class QuoteWriter {
    private final QuoteRepository repository;

    QuoteWriter(QuoteRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void insert(Instant fetchedAt, QuoteBatch batch) {
        for (FixtureQuote quote : batch.quotes()) {
            repository.insert(fetchedAt, batch.cycle(), batch.sampleIndex(), batch.marketTime(),
                    quote.symbol(), quote.price());
        }
    }
}
