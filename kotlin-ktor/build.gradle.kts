plugins {
    kotlin("jvm") version "2.2.20"
    application
}
repositories { mavenCentral() }
val ktorVersion = "3.6.0"
dependencies {
    implementation("io.ktor:ktor-server-core-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-netty-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-content-negotiation-jvm:$ktorVersion")
    implementation("io.ktor:ktor-serialization-jackson-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-status-pages-jvm:$ktorVersion")
    implementation("io.ktor:ktor-server-cors-jvm:$ktorVersion")
    implementation("com.zaxxer:HikariCP:6.3.0")
    implementation("com.h2database:h2:2.3.232")
    implementation("org.postgresql:postgresql:42.7.7")
    testImplementation(kotlin("test"))
}
kotlin { jvmToolchain(21) }
application { mainClass.set("dev.northstar.ApplicationKt") }
tasks.test { useJUnitPlatform() }
