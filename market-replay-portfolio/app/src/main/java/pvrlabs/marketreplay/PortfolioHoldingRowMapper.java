package pvrlabs.marketreplay;

import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

final class PortfolioHoldingRowMapper implements RowMapper<PricedHolding> {
    @Override
    public PricedHolding mapRow(ResultSet row, int rowNumber) throws SQLException {
        return new PricedHolding(
                row.getString("symbol"),
                row.getBigDecimal("quantity"),
                row.getBigDecimal("price"));
    }
}
