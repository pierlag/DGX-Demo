// Game variables
const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');
const startScreen = document.getElementById('start-screen');
const gameOverScreen = document.getElementById('game-over-screen');
const scoreDisplay = document.getElementById('score-display');
const finalScore = document.getElementById('final-score');

let gameRunning = false;
let score = 0;
let player = {
    x: canvas.width / 2 - 25,
    y: canvas.height - 60,
    width: 50,
    height: 40,
    speed: 7,
    color: '#00FFFF'
};

let bullets = [];
let enemies = [];
let keys = {};
let enemySpawnTimer = 0;
let enemySpawnInterval = 60; // frames

// Initialize game
function init() {
    player.x = canvas.width / 2 - 25;
    player.y = canvas.height - 60;
    bullets = [];
    enemies = [];
    score = 0;
    scoreDisplay.textContent = `Score: ${score}`;
}

// Start the game
function startGame() {
    init();
    gameRunning = true;
    startScreen.style.display = 'none';
    gameOverScreen.style.display = 'none';
    gameLoop();
}

// Restart the game
function restartGame() {
    init();
    gameRunning = true;
    gameOverScreen.style.display = 'none';
    gameLoop();
}

// Handle keyboard input
document.addEventListener('keydown', (e) => {
    keys[e.key] = true;
    
    // Allow starting a new game with spacebar when game is over
    if (!gameRunning && e.key === ' ') {
        restartGame();
    }
});

document.addEventListener('keyup', (e) => {
    keys[e.key] = false;
});

// Create bullets
function shoot() {
    bullets.push({
        x: player.x + player.width / 2 - 3,
        y: player.y,
        width: 6,
        height: 15,
        speed: 10,
        color: '#FFFF00'
    });
}

// Spawn enemies
function spawnEnemy() {
    enemies.push({
        x: Math.random() * (canvas.width - 40),
        y: -40,
        width: 40,
        height: 40,
        speed: 2 + Math.random() * 3,
        color: '#FF0000'
    });
}

// Update game state
function update() {
    if (!gameRunning) return;
    
    // Move player
    if (keys['ArrowLeft'] && player.x > 0) {
        player.x -= player.speed;
    }
    if (keys['ArrowRight'] && player.x < canvas.width - player.width) {
        player.x += player.speed;
    }
    if (keys['ArrowUp'] && player.y > 0) {
        player.y -= player.speed;
    }
    if (keys['ArrowDown'] && player.y < canvas.height - player.height) {
        player.y += player.speed;
    }
    
    // Shoot bullets
    if (keys[' ']) {
        // Limit bullet firing rate
        if (bullets.length === 0 || bullets[bullets.length - 1].y < player.y - 20) {
            shoot();
        }
    }
    
    // Update bullets
    for (let i = bullets.length - 1; i >= 0; i--) {
        bullets[i].y -= bullets[i].speed;
        
        // Remove bullets that go off screen
        if (bullets[i].y < 0) {
            bullets.splice(i, 1);
            continue;
        }
        
        // Check bullet-enemy collisions
        for (let j = enemies.length - 1; j >= 0; j--) {
            if (checkCollision(bullets[i], enemies[j])) {
                // Remove both bullet and enemy
                bullets.splice(i, 1);
                enemies.splice(j, 1);
                score += 10;
                scoreDisplay.textContent = `Score: ${score}`;
                break;
            }
        }
    }
    
    // Update enemies
    for (let i = enemies.length - 1; i >= 0; i--) {
        enemies[i].y += enemies[i].speed;
        
        // Remove enemies that go off screen
        if (enemies[i].y > canvas.height) {
            enemies.splice(i, 1);
            continue;
        }
        
        // Check player-enemy collisions
        if (checkCollision(player, enemies[i])) {
            gameOver();
        }
    }
    
    // Spawn enemies
    enemySpawnTimer++;
    if (enemySpawnTimer >= enemySpawnInterval) {
        spawnEnemy();
        enemySpawnTimer = 0;
        // Make the game progressively harder
        if (enemySpawnInterval > 20) {
            enemySpawnInterval -= 0.05;
        }
    }
}

// Check collision between two rectangles
function checkCollision(rect1, rect2) {
    return rect1.x < rect2.x + rect2.width &&
           rect1.x + rect1.width > rect2.x &&
           rect1.y < rect2.y + rect2.height &&
           rect1.y + rect1.height > rect2.y;
}

// Render game
function render() {
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (!gameRunning) return;
    
    // Draw player
    ctx.fillStyle = player.color;
    ctx.fillRect(player.x, player.y, player.width, player.height);
    
    // Draw player cockpit
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(player.x + 20, player.y + 5, 10, 10);
    
    // Draw bullets
    ctx.fillStyle = '#FFFF00';
    for (let bullet of bullets) {
        ctx.fillRect(bullet.x, bullet.y, bullet.width, bullet.height);
    }
    
    // Draw enemies
    ctx.fillStyle = '#FF0000';
    for (let enemy of enemies) {
        ctx.fillRect(enemy.x, enemy.y, enemy.width, enemy.height);
        
        // Draw enemy details
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(enemy.x + 10, enemy.y + 10, 5, 5);
        ctx.fillRect(enemy.x + 25, enemy.y + 10, 5, 5);
        ctx.fillStyle = '#FF0000';
    }
}

// Game over function
function gameOver() {
    gameRunning = false;
    finalScore.textContent = `Score: ${score}`;
    gameOverScreen.style.display = 'flex';
}

// Main game loop
function gameLoop() {
    if (!gameRunning) return;
    
    update();
    render();
    
    requestAnimationFrame(gameLoop);
}