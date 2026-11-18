package pvrlabs.marketreplay;

import jakarta.enterprise.context.ApplicationScoped;

import pvrlabs.coilbase.RepositoryContext;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;

@ApplicationScoped
class PortfolioService {
    private static final Set<String> SUPPORTED_SYMBOLS = Set.of("AAPL", "GOOG", "NVDA");
    private static final BigDecimal QUANTITY_LIMIT = new BigDecimal("10000000000000");
    private final PortfolioRepository repository;
    private final RepositoryContext context;

    PortfolioService(PortfolioRepository repository, RepositoryContext context) {
        this.repository = repository;
        this.context = context;
    }

    public Portfolio portfolio(long userId) {
        if (!repository.userExists(userId)) {
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

    public void setQuantity(long userId, String symbol, BigDecimal quantity) {
        context.useTransaction(
                handle -> {
                    validateHolding(symbol, quantity);
                    // Serialize edits for this user, including insertion/deletion of absent
                    // holdings.
                    // The service transaction holds the lock through commit: last committed
                    // assignment wins.
                    if (!repository.lockUser(userId)) {
                        throw new UserNotFoundException();
                    }
                    if (quantity.signum() == 0) {
                        repository.deleteHolding(userId, symbol);
                    } else {
                        repository.saveHolding(userId, symbol, quantity);
                    }
                });
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
