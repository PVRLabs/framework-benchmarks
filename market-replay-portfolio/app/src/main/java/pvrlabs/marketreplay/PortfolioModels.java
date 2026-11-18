package pvrlabs.marketreplay;

import java.math.BigDecimal;
import java.util.List;

// A persisted holding joined to its latest quote. Price is null until a quote is available.
record PricedHolding(String symbol, BigDecimal quantity, BigDecimal price) {}

record Holding(String symbol, BigDecimal quantity, BigDecimal price, BigDecimal value) {}

record Portfolio(long userId, List<Holding> holdings, BigDecimal totalValue) {}

record Valuation(long userId, BigDecimal totalValue) {}
