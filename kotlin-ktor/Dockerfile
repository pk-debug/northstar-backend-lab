# Build context MUST be repository root.
FROM gradle:8.14-jdk21 AS build
WORKDIR /home/gradle/project
COPY kotlin-ktor/ ./
RUN gradle installDist --no-daemon
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /home/gradle/project/build/install/northstar-kotlin-ktor /app
EXPOSE 8082
CMD ["/app/bin/northstar-kotlin-ktor"]
