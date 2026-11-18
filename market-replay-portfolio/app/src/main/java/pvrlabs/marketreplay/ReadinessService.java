package pvrlabs.marketreplay;

import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

@Service
class ReadinessService {
    private final PortfolioRepository portfolios;
    private final QuoteRepository quotes;

    ReadinessService(PortfolioRepository portfolios, QuoteRepository quotes) {
        this.portfolios = portfolios;
        this.quotes = quotes;
    }

    boolean isReady() {
        try {
            return portfolios.findSeedUserCount().isPresent() && quotes.hasMarketPrices();
        } catch (DataAccessException exception) {
            // Readiness requires current database access, not just previous initialization.
            return false;
        }
    }
}
