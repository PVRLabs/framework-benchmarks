package pvrlabs.marketreplay;

import io.micronaut.core.annotation.Introspected;
import io.micronaut.core.annotation.Nullable;

import java.math.BigDecimal;
import java.util.List;

// A persisted holding joined to its latest quote. Price is null until a quote is available.
@Introspected
record PricedHolding(String symbol, BigDecimal quantity, @Nullable BigDecimal price) {}

record Holding(String symbol, BigDecimal quantity, BigDecimal price, BigDecimal value) {}

record Portfolio(long userId, List<Holding> holdings, BigDecimal totalValue) {}

record Valuation(long userId, BigDecimal totalValue) {}
