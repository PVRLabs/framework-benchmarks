package pvrlabs.marketreplay;

import jakarta.inject.Singleton;

import jakarta.transaction.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;

@Singleton
class PortfolioService {
    private static final Set<String> SUPPORTED_SYMBOLS = Set.of("AAPL", "GOOG", "NVDA");
    private static final BigDecimal QUANTITY_LIMIT = new BigDecimal("10000000000000");
    private final PortfolioRepository repository;

    PortfolioService(PortfolioRepository repository) {
        this.repository = repository;
    }

    public Portfolio portfolio(long userId) {
        if (!repository.existsById(userId)) {
            throw new UserNotFoundException();
        }
        List<Holding> holdings =
                repository.findHoldingsWithLatestPrices(userId).stream()
                        .map(this::valueHolding)
                        .toList();
        BigDecimal total =
                holdings.stream().map(Holding::value).reduce(BigDecimal.ZERO, BigDecimal::add);
        return new Portfolio(userId, holdings, total);
    }

    @Transactional
    public void setQuantity(long userId, String symbol, BigDecimal quantity) {
        validateHolding(symbol, quantity);
        // Hold the user lock through commit, including edits to absent holdings.
        if (repository.lockUser(userId).isEmpty()) {
            throw new UserNotFoundException();
        }
        if (quantity.signum() == 0) {
            repository.deleteHolding(userId, symbol);
        } else {
            repository.saveHolding(userId, symbol, quantity);
        }
    }

    private void validateHolding(String symbol, BigDecimal quantity) {
        if (symbol == null
                || !SUPPORTED_SYMBOLS.contains(symbol)
                || quantity == null
                || quantity.signum() < 0
                || quantity.stripTrailingZeros().scale() > 6
                || quantity.compareTo(QUANTITY_LIMIT) >= 0) {
            throw new InvalidHoldingException();
        }
    }

    private Holding valueHolding(PricedHolding holding) {
        if (holding.price() == null) {
            throw new MarketPricesUnavailableException();
        }
        return new Holding(
                holding.symbol(),
                holding.quantity(),
                holding.price(),
                holding.quantity().multiply(holding.price()));
    }
}
