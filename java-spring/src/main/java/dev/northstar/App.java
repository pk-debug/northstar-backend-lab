package dev.northstar;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** WHAT: Java entry point; WHY: dependency injection; WHO: Northstar API;
 * WHEN: startup; WHERE: Spring Boot JVM; HOW: auto-configured HTTP + JDBC;
 * HOW MUCH: runs with local H2 or PostgreSQL.
 */
@SpringBootApplication
public class App {
    /** Start the embedded server and let Spring construct services and controllers. */
    public static void main(String[] args) { SpringApplication.run(App.class, args); }
}
