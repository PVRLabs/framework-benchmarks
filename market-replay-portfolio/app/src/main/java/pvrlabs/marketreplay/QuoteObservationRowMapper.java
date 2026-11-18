package pvrlabs.marketreplay;

import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

final class QuoteObservationRowMapper implements RowMapper<QuoteObservation> {
    @Override
    public QuoteObservation mapRow(ResultSet row, int rowNumber) throws SQLException {
        return new QuoteObservation(
                row.getLong("id"),
                row.getTimestamp("fetched_at").toInstant(),
                row.getInt("cycle"),
                row.getInt("sample_index"),
                row.getString("market_time"),
                row.getString("symbol"),
                row.getBigDecimal("price"));
    }
}
