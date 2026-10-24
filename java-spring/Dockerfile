# Build context MUST be repository root: docker build -f java-spring/Dockerfile .
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app
COPY java-spring/pom.xml .
RUN mvn dependency:go-offline -B
COPY java-spring/src ./src
RUN mvn package -q -DskipTests
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/target/java-spring-1.0.0.jar app.jar
EXPOSE 8081
ENTRYPOINT ["java","-jar","app.jar"]
