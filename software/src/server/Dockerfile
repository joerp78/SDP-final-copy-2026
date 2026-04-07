# Build stage
FROM gradle:8-jdk17 AS build

WORKDIR /app

COPY gradlew ./
COPY gradle ./gradle

RUN chmod +x gradlew

COPY build.gradle* ./
COPY settings.gradle* ./

RUN ./gradlew dependencies --no-daemon || true

COPY src ./src

RUN ./gradlew build --no-daemon -x test

# Run stage
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

COPY --from=build /app/build/libs/*.jar app.jar

EXPOSE 8081  

ENTRYPOINT ["java", "-jar", "app.jar"]
