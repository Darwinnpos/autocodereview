# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start the development server
python run.py
# Or with environment variables
FLASK_ENV=development python run.py

# Production deployment
export FLASK_ENV=production
export SECRET_KEY=your-secret-key
export DATABASE_PATH=/path/to/reviews.db
python run.py
```

### Installation and Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Environment setup
export FLASK_ENV=development  # or production
export HOST=0.0.0.0
export PORT=5000
```

### Database Management
The application uses SQLite databases:
- `auth.db` - User authentication and configuration
- `reviews.db` - Code review records and analysis results

## Architecture Overview

This is a Flask-based automated code review system that integrates with GitLab to perform AI-powered code analysis on Merge Requests.

### Core Components

**Flask Application Structure:**
- `app/__init__.py` - Application factory with blueprint registration
- `run.py` - Application entry point with environment configuration

**API Layer:**
- `app/api/auth.py` - User authentication and profile management
- `app/api/review.py` - Code review operations and status endpoints

**Service Layer:**
- `app/services/review_service.py` - Main orchestrator for the review process
- `app/services/gitlab_client.py` - GitLab API integration
- `app/services/ai_analyzer.py` - AI-powered code analysis using configurable AI APIs
- `app/services/comment_generator.py` - Comment formatting and generation

**Data Layer:**
- `app/models/auth.py` - User authentication and configuration data models
- `app/models/review.py` - Review records and analysis results data models
- `app/utils/db_manager.py` - Database connection management with pooling

### Key Architectural Patterns

**Configuration Management:**
- Environment-based configuration in `config/` directory
- User-specific AI and GitLab configurations stored in auth database
- Support for multiple AI providers (OpenAI, custom APIs)

**Database Design:**
- Separate databases for authentication and review data
- Connection pooling for performance
- Progress tracking for long-running review operations

**Review Workflow:**
1. User authentication and configuration validation
2. GitLab MR parsing and change detection
3. AI analysis of modified code with configurable severity levels
4. Comment generation and storage as "pending" status
5. User confirmation before posting comments to GitLab

**AI Integration:**
- Configurable AI API endpoints and models
- Context-aware analysis using file content, diffs, and MR metadata
- Severity-based filtering (strict/standard/relaxed modes)
- Support for multiple programming languages

### Web Interface

**Template Structure:**
- `app/templates/base.html` - Common layout and navigation
- `app/templates/index.html` - Main review interface
- `app/templates/profile.html` - User configuration management
- `app/templates/admin.html` - Administrative functions

**Frontend Features:**
- Real-time progress tracking during reviews
- Comment preview and bulk confirmation
- GitLab configuration testing
- Review history and statistics

### Security Considerations

- User authentication with password hashing
- GitLab access token encryption in database
- AI API key secure storage
- Input validation for MR URLs and user data
- Rate limiting and connection timeouts

### Database Schema Notes

The `auth.db` contains user profiles with GitLab and AI configurations, while `reviews.db` stores review history, analysis results, and pending comments. The system maintains referential integrity between reviews and their associated issues/comments.

### Environment Configuration

The application supports development and production environments with different configurations for logging, database paths, and security settings. See `config/` directory for environment-specific settings.