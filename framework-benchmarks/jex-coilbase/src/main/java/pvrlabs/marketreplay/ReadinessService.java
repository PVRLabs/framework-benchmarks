package pvrlabs.marketreplay;

final class ReadinessService {
    private final PortfolioRepository portfolios;
    private final QuoteRepository quotes;

    ReadinessService(PortfolioRepository portfolios, QuoteRepository quotes) {
        this.portfolios = portfolios;
        this.quotes = quotes;
    }

    boolean isReady() {
        try {
            return portfolios.findSeedUserCount().isPresent() && quotes.hasMarketPrices();
        } catch (RuntimeException failure) {
            return false;
        }
    }
}
