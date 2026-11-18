package pvrlabs.marketreplay;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest(properties = {"market.poll-enabled=false", "portfolio.seed-users=10",
        "spring.datasource.url=${TEST_DB_URL:jdbc:h2:mem:portfolio-test;DB_CLOSE_DELAY=-1}"})
@AutoConfigureMockMvc
class DatabaseCorrectnessTest {
    @Autowired JdbcClient jdbc;
    @Autowired QuoteRepository quotes;
    @Autowired QuoteSyncService sync;
    @Autowired PortfolioService portfolios;
    @Autowired TransactionTemplate transactions;
    @Autowired MockMvc http;
    @MockitoBean QuoteClient client;

    QuoteBatch batch(int sample, String aapl) {
        return new QuoteBatch(0, java.time.LocalTime.of(9,30).plusMinutes(sample).toString(), sample,
                List.of(new FixtureQuote("AAPL",new BigDecimal(aapl)),
                        new FixtureQuote("GOOG",new BigDecimal("2.25")),
                        new FixtureQuote("NVDA",new BigDecimal("3.5"))));
    }

    @BeforeEach void clean() {
        jdbc.sql("DELETE FROM quote_samples").update();
        jdbc.sql("DELETE FROM portfolio_holdings WHERE user_id IN (1,2)").update();
    }

    @Test void seededPortfolio() {
        assertThat(jdbc.sql("SELECT COUNT(*) FROM users").query(Long.class).single()).isEqualTo(10);
        assertThat(jdbc.sql("SELECT COUNT(*) FROM portfolio_holdings WHERE user_id=10").query(Long.class).single()).isEqualTo(3);
        assertThat(jdbc.sql("SELECT quantity FROM portfolio_holdings WHERE user_id=10 AND symbol='AAPL'")
                .query(BigDecimal.class).single()).isEqualByComparingTo("71");
    }

    @Test void ingestionLatestValuationAndAtomicRollback() throws Exception {
        given(client.fetch()).willReturn(batch(0,"1.25"));
        sync.pollOnce();
        assertThat(quotes.count()).isEqualTo(3);
        portfolios.setQuantity(1,"AAPL",new BigDecimal("10.125"));
        portfolios.setQuantity(1,"GOOG",new BigDecimal("2"));
        assertThat(portfolios.portfolio(1).totalValue()).isEqualByComparingTo("17.15625");
        given(client.fetch()).willReturn(batch(1,"2.50"));
        sync.pollOnce();
        assertThat(quotes.latest()).extracting(QuoteObservation::sampleIndex).containsOnly(1);
        assertThat(portfolios.portfolio(1).totalValue()).isEqualByComparingTo("29.8125");
        var bad = new QuoteBatch(0,"09:30",0,List.of(new FixtureQuote("AAPL",BigDecimal.ONE),
                new FixtureQuote("GOOG",BigDecimal.ONE),new FixtureQuote("NVDA",null)));
        assertThatThrownBy(() -> quotes.insert(Instant.now(),bad)).isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
        assertThat(quotes.count()).isEqualTo(6);
        for (var malformed : List.of(bad, new QuoteBatch(-1,"09:30",0,batch(0,"1").quotes()),
                new QuoteBatch(0,"09:31",0,batch(0,"1").quotes()),
                new QuoteBatch(0,"09:30",0,List.of(new FixtureQuote("AAPL",BigDecimal.ONE),
                        new FixtureQuote("AAPL",BigDecimal.ONE),new FixtureQuote("NVDA",BigDecimal.ONE))))) {
            given(client.fetch()).willReturn(malformed);
            assertThatThrownBy(() -> sync.pollOnce()).isInstanceOf(java.io.IOException.class);
            assertThat(quotes.count()).isEqualTo(6);
        }
        given(client.fetch()).willThrow(new java.io.IOException("fixture unavailable"));
        assertThat(portfolios.portfolio(1).totalValue()).isEqualByComparingTo("29.8125");
    }

    @Test void restValidationAndRemoval() throws Exception {
        http.perform(get("/readyz")).andExpect(status().isServiceUnavailable());
        quotes.insert(Instant.now(), batch(0,"1.25"));
        http.perform(get("/readyz")).andExpect(status().isOk());
        http.perform(get("/users/999/portfolio")).andExpect(status().isNotFound());
        http.perform(get("/users/999/valuation")).andExpect(status().isNotFound());
        http.perform(put("/users/999/holdings/AAPL").contentType("application/json").content("{\"quantity\":1}"))
                .andExpect(status().isNotFound());
        for (String body : List.of("{}","null","{","{\"quantity\":-1}","{\"quantity\":0.0000001}","{\"quantity\":10000000000000}")) {
            http.perform(put("/users/1/holdings/AAPL").contentType("application/json").content(body)).andExpect(status().isBadRequest());
        }
        http.perform(put("/users/1/holdings/MSFT").contentType("application/json").content("{\"quantity\":1}"))
                .andExpect(status().isBadRequest());
        for (String quantity : List.of("10", "10", "12.345678", "0", "0")) {
            http.perform(put("/users/1/holdings/AAPL").contentType("application/json").content("{\"quantity\":"+quantity+"}"))
                    .andExpect(status().isNoContent());
            if (!quantity.equals("0")) assertThat(portfolios.portfolio(1).holdings().getFirst().quantity()).isEqualByComparingTo(quantity);
        }
        assertThat(portfolios.portfolio(1).holdings()).isEmpty();
        assertThat(portfolios.portfolio(1).totalValue()).isEqualByComparingTo("0");
    }

    @Test void missingPricesRemainDistinctFromAnEmptyPortfolio() throws Exception {
        portfolios.setQuantity(1, "AAPL", BigDecimal.TEN);
        assertThatThrownBy(() -> portfolios.portfolio(1)).isInstanceOf(MarketPricesUnavailableException.class);
        http.perform(get("/users/1/portfolio"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.detail").value("Market prices unavailable"));
        http.perform(get("/users/1/valuation")).andExpect(status().isServiceUnavailable());
        portfolios.setQuantity(1, "AAPL", BigDecimal.ZERO);
        assertThat(portfolios.portfolio(1).totalValue()).isEqualByComparingTo("0");
        http.perform(get("/users/1/valuation")).andExpect(status().isOk());
        http.perform(get("/readyz")).andExpect(status().isServiceUnavailable());
    }

    @Test void concurrentSameAndDifferentHoldingsIncludingInsertDelete() throws Exception {
        quotes.insert(Instant.now(), batch(0,"1.25"));
        try (var executor = Executors.newFixedThreadPool(8)) {
            var start = new CountDownLatch(1);
            var tasks = new java.util.ArrayList<Future<?>>();
            for (int i=0;i<32;i++) {
                int index=i;
                tasks.add(executor.submit(() -> {
                    start.await();
                    portfolios.setQuantity(1,"AAPL",BigDecimal.valueOf(index));
                    portfolios.setQuantity(1,"GOOG",BigDecimal.valueOf(index+1));
                    portfolios.setQuantity(2,"NVDA",BigDecimal.valueOf(index+2));
                    return null;
                }));
            }
            start.countDown();
            for (var task : tasks) task.get(20,TimeUnit.SECONDS);
        }
        assertThat(portfolios.portfolio(1).holdings()).hasSizeBetween(1,2);
        assertThat(portfolios.portfolio(2).holdings()).hasSize(1);
        portfolios.setQuantity(1,"AAPL",new BigDecimal("42"));
        assertThat(portfolios.portfolio(1).holdings().getFirst().quantity()).isEqualByComparingTo("42");
    }

    @Test void lastCommitWinsAndLockIsHeldUntilCommit() throws Exception {
        var locked = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try (var executor = Executors.newFixedThreadPool(2)) {
            var first = executor.submit(() -> transactions.executeWithoutResult(status -> {
                portfolios.setQuantity(1,"AAPL",BigDecimal.TEN);
                locked.countDown();
                try { if (!release.await(5,TimeUnit.SECONDS)) throw new IllegalStateException("test timeout"); }
                catch (InterruptedException e) { throw new RuntimeException(e); }
            }));
            assertThat(locked.await(5,TimeUnit.SECONDS)).isTrue();
            var secondStarted = new CountDownLatch(1);
            var second = executor.submit(() -> { secondStarted.countDown(); portfolios.setQuantity(1,"AAPL",BigDecimal.ONE); });
            assertThat(secondStarted.await(5,TimeUnit.SECONDS)).isTrue();
            try { assertThatThrownBy(() -> second.get(150,TimeUnit.MILLISECONDS)).isInstanceOf(TimeoutException.class); }
            finally { release.countDown(); }
            first.get(5,TimeUnit.SECONDS);
            second.get(5,TimeUnit.SECONDS);
            assertThat(jdbc.sql("SELECT quantity FROM portfolio_holdings WHERE user_id=1 AND symbol='AAPL'")
                    .query(BigDecimal.class).single()).isEqualByComparingTo("1");
        } finally { release.countDown(); }
    }

    @Test void historyBoundedAcrossWrap() {
        for (int i=0;i<391;i++) quotes.insert(Instant.now(),new QuoteBatch(i/390,
                java.time.LocalTime.of(9,30).plusMinutes(i%390).toString(),i%390,batch(0,"1.25").quotes()));
        assertThat(quotes.history()).hasSize(1170);
        assertThat(quotes.latest()).extracting(QuoteObservation::cycle).containsOnly(1);
    }
}
