"""
System Health Monitor - Background task-based monitoring
Monitors database, user monitor, channels, and system performance
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType

logger = logging.getLogger(__name__)

class HealthMonitor:
    def __init__(self, config: BotConfig, data_manager: SQLiteManager):
        self.config = config
        self.data_manager = data_manager
        self.event_bus = get_event_bus()
        
        # Health status tracking
        self.last_health_check = None
        self.component_status = {}
        self.error_counts = {}
        self.performance_metrics = {}
        
        logger.info("Health monitor initialized")
    
    async def run_health_check(self, context=None):
        """Main health check method - called by job queue"""
        try:
            logger.debug("🏥 Running scheduled health check...")
            
            # Perform all health checks
            results = await self._perform_comprehensive_health_check(context)
            
            # Process results
            await self._process_health_results(results, context)
            
            # Update status
            self.last_health_check = datetime.now()
            
            logger.debug("✅ Health check completed")
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'health_monitor',
                'error': str(e),
                'operation': 'run_health_check'
            }, source='health_monitor')
    
    async def _perform_comprehensive_health_check(self, context) -> Dict:
        """Perform comprehensive health check of all components"""
        results = {
            'database': await self._check_database_health(),
            'user_monitor': await self._check_user_monitor_health(context),
            'channels': await self._check_channels_health(context),
            'system': await self._check_system_health(),
            'performance': await self._check_performance_metrics()
        }
        
        return results
    
    async def _check_database_health(self) -> Dict:
        """Check database health and performance"""
        try:
            start_time = datetime.now()
            
            # Test basic connectivity
            stats = await self.data_manager.get_system_stats()
            
            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds() * 1000  # ms
            
            # Check for basic data integrity
            users_count = stats.get('total_users', 0)
            channels_count = sum(stats.get('channels', {}).values())
            
            status = {
                'status': 'healthy',
                'response_time_ms': response_time,
                'users_count': users_count,
                'channels_count': channels_count,
                'last_checked': datetime.now().isoformat(),
                'issues': []
            }
            
            # Performance warnings
            if response_time > 100:  # > 100ms
                status['issues'].append(f"Slow database response: {response_time:.1f}ms")
                if response_time > 1000:  # > 1s
                    status['status'] = 'degraded'
            
            # Data integrity checks
            if users_count == 0 and channels_count > 0:
                status['issues'].append("No users found but channels exist")
                status['status'] = 'warning'
            
            return status
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'last_checked': datetime.now().isoformat(),
                'issues': [f"Database connection failed: {str(e)}"]
            }
    
    async def _check_user_monitor_health(self, context) -> Dict:
        """Check user monitor health"""
        try:
            if not context or not context.bot_data:
                return {
                    'status': 'not_available',
                    'reason': 'No context available',
                    'last_checked': datetime.now().isoformat()
                }
            
            user_monitor = context.bot_data.get('user_monitor')
            if not user_monitor:
                return {
                    'status': 'disabled',
                    'reason': 'User monitor not configured',
                    'last_checked': datetime.now().isoformat()
                }
            
            # Check connection status
            is_connected = user_monitor.is_connected()
            auth_status = user_monitor.get_auth_status()
            
            # Get monitoring stats
            try:
                monitor_stats = await user_monitor.get_monitor_stats()
            except Exception:
                monitor_stats = {}
            
            status = {
                'status': 'healthy',
                'connected': is_connected,
                'auth_status': auth_status,
                'monitored_channels': monitor_stats.get('monitored_channels', 0),
                'last_checked': datetime.now().isoformat(),
                'issues': []
            }
            
            # Determine overall status
            if auth_status != 'authenticated':
                status['status'] = 'needs_auth'
                status['issues'].append(f"Authentication required: {auth_status}")
            elif not is_connected:
                status['status'] = 'disconnected'
                status['issues'].append("User monitor not connected")
            elif monitor_stats.get('reconnect_attempts', 0) > 2:
                status['status'] = 'unstable'
                status['issues'].append(f"Multiple reconnection attempts: {monitor_stats['reconnect_attempts']}")
            
            return status
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'last_checked': datetime.now().isoformat(),
                'issues': [f"Health check failed: {str(e)}"]
            }
    
    async def _check_channels_health(self, context) -> Dict:
        """Check channel health and bot permissions"""
        try:
            # Get all bot channels
            bot_channels = await self.data_manager.get_simple_bot_channels()
            
            if not bot_channels:
                return {
                    'status': 'no_channels',
                    'bot_channels_count': 0,
                    'valid_channels': 0,
                    'last_checked': datetime.now().isoformat()
                }
            
            # Sample a few channels for health check (don't check all to avoid rate limits)
            sample_size = min(5, len(bot_channels))
            sample_channels = bot_channels[:sample_size]
            
            valid_channels = 0
            issues = []
            
            if context and context.bot:
                for chat_id in sample_channels:
                    try:
                        # Quick check with timeout
                        chat = await asyncio.wait_for(
                            context.bot.get_chat(chat_id),
                            timeout=self.config.CHANNEL_VALIDATION_TIMEOUT
                        )
                        
                        # Check admin status
                        try:
                            bot_member = await asyncio.wait_for(
                                context.bot.get_chat_member(chat.id, context.bot.id),
                                timeout=5
                            )
                            is_admin = bot_member.status in ['administrator', 'creator']
                            
                            if is_admin:
                                valid_channels += 1
                            else:
                                display_name = await self.data_manager.get_channel_display_name(chat_id)
                                issues.append(f"Not admin in {display_name}")
                                
                        except Exception:
                            display_name = await self.data_manager.get_channel_display_name(chat_id)
                            issues.append(f"Cannot check permissions in {display_name}")
                    
                    except asyncio.TimeoutError:
                        display_name = await self.data_manager.get_channel_display_name(chat_id)
                        issues.append(f"Timeout accessing {display_name}")
                    except Exception as e:
                        display_name = await self.data_manager.get_channel_display_name(chat_id)
                        issues.append(f"Error accessing {display_name}: {str(e)[:50]}")
            
            # Determine status
            if valid_channels == sample_size:
                status = 'healthy'
            elif valid_channels > 0:
                status = 'partial'
            else:
                status = 'issues'
            
            return {
                'status': status,
                'bot_channels_count': len(bot_channels),
                'sample_checked': sample_size,
                'valid_channels': valid_channels,
                'issues': issues,
                'last_checked': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'last_checked': datetime.now().isoformat(),
                'issues': [f"Channel health check failed: {str(e)}"]
            }
    
    async def _check_system_health(self) -> Dict:
        """Check overall system health"""
        try:
            # Get error monitoring stats if available
            error_stats = {}
            try:
                from utils.error_monitor import get_error_collector
                error_collector = get_error_collector()
                if error_collector:
                    error_stats = error_collector.get_error_stats()
            except Exception:
                pass
            
            # Memory and performance indicators
            try:
                import psutil
                memory_percent = psutil.virtual_memory().percent
                cpu_percent = psutil.cpu_percent(interval=1)
            except Exception:
                memory_percent = 0
                cpu_percent = 0
            
            status = {
                'status': 'healthy',
                'memory_usage_percent': memory_percent,
                'cpu_usage_percent': cpu_percent,
                'error_stats': error_stats,
                'uptime_hours': self._get_uptime_hours(),
                'last_checked': datetime.now().isoformat(),
                'issues': []
            }
            
            # Check for issues
            if memory_percent > 90:
                status['status'] = 'warning'
                status['issues'].append(f"High memory usage: {memory_percent:.1f}%")
            
            if cpu_percent > 80:
                status['status'] = 'warning'
                status['issues'].append(f"High CPU usage: {cpu_percent:.1f}%")
            
            if error_stats.get('critical', 0) > 0:
                status['status'] = 'critical'
                status['issues'].append(f"Critical errors: {error_stats['critical']}")
            elif error_stats.get('total', 0) > 50:
                status['status'] = 'warning'
                status['issues'].append(f"Many errors (24h): {error_stats['total']}")
            
            return status
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'last_checked': datetime.now().isoformat(),
                'issues': [f"System health check failed: {str(e)}"]
            }
    
    async def _check_performance_metrics(self) -> Dict:
        """Check performance metrics"""
        try:
            # Get recent forwarding stats
            stats = await self.data_manager.get_system_stats()
            
            # Calculate performance indicators
            forwards_24h = stats.get('forwards_24h', 0)
            total_users = stats.get('total_users', 0)
            
            # Estimate message processing rate
            processing_rate = forwards_24h / 24 if forwards_24h > 0 else 0  # per hour
            
            metrics = {
                'forwards_24h': forwards_24h,
                'forwards_per_hour': processing_rate,
                'total_users': total_users,
                'active_users_percent': self._calculate_active_users_percent(stats),
                'avg_keywords_per_user': self._calculate_avg_keywords(stats),
                'last_calculated': datetime.now().isoformat()
            }
            
            return metrics
            
        except Exception as e:
            return {
                'error': str(e),
                'last_calculated': datetime.now().isoformat()
            }
    
    def _get_uptime_hours(self) -> float:
        """Calculate approximate uptime"""
        try:
            import psutil
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            return uptime.total_seconds() / 3600
        except Exception:
            return 0.0
    
    def _calculate_active_users_percent(self, stats: Dict) -> float:
        """Calculate percentage of active users"""
        try:
            total_users = stats.get('total_users', 0)
            total_keywords = stats.get('total_keywords', 0)
            
            if total_users == 0:
                return 0.0
            
            # Users with keywords are considered active
            users_with_keywords = min(total_keywords, total_users)  # rough estimate
            return (users_with_keywords / total_users) * 100
            
        except Exception:
            return 0.0
    
    def _calculate_avg_keywords(self, stats: Dict) -> float:
        """Calculate average keywords per user"""
        try:
            total_users = stats.get('total_users', 0)
            total_keywords = stats.get('total_keywords', 0)
            
            if total_users == 0:
                return 0.0
            
            return total_keywords / total_users
            
        except Exception:
            return 0.0
    
    async def _process_health_results(self, results: Dict, context):
        """Process health check results and take action if needed"""
        try:
            # Update component status
            self.component_status = results
            
            # Determine overall system health
            overall_status = self._determine_overall_status(results)
            
            # Check for critical issues that need immediate attention
            critical_issues = self._identify_critical_issues(results)
            
            # Notify admin if there are critical issues
            if critical_issues and self.config.AUTHORIZED_ADMIN_ID:
                await self._notify_admin_of_issues(critical_issues, context)
            
            # Emit health check event
            await self.event_bus.emit(EventType.SYSTEM_HEALTH_CHECK, {
                'overall_status': overall_status,
                'component_status': results,
                'critical_issues': critical_issues,
                'timestamp': datetime.now().isoformat()
            }, source='health_monitor')
            
            # Log summary
            self._log_health_summary(overall_status, results)
            
        except Exception as e:
            logger.error(f"Error processing health results: {e}")
    
    def _determine_overall_status(self, results: Dict) -> str:
        """Determine overall system health status"""
        statuses = []
        
        for component, result in results.items():
            if isinstance(result, dict):
                status = result.get('status', 'unknown')
                statuses.append(status)
        
        # Priority: critical > failed > error > degraded > warning > needs_auth > healthy
        if 'critical' in statuses or 'failed' in statuses:
            return 'critical'
        elif 'error' in statuses:
            return 'error' 
        elif 'degraded' in statuses:
            return 'degraded'
        elif 'warning' in statuses or 'partial' in statuses or 'unstable' in statuses:
            return 'warning'
        elif 'needs_auth' in statuses:
            return 'needs_attention'
        else:
            return 'healthy'
    
    def _identify_critical_issues(self, results: Dict) -> List[str]:
        """Identify issues that need immediate attention"""
        critical_issues = []
        
        for component, result in results.items():
            if not isinstance(result, dict):
                continue
            
            status = result.get('status', 'unknown')
            issues = result.get('issues', [])
            
            # Critical database issues
            if component == 'database' and status in ['failed', 'critical']:
                critical_issues.append(f"🚨 Database: {result.get('error', 'Connection failed')}")
            
            # System resource issues
            elif component == 'system':
                if status == 'critical':
                    critical_issues.extend([f"🚨 System: {issue}" for issue in issues])
                elif result.get('memory_usage_percent', 0) > 95:
                    critical_issues.append(f"🚨 Memory usage critical: {result['memory_usage_percent']:.1f}%")
            
            # User monitor authentication issues (less critical but important)
            elif component == 'user_monitor' and status == 'needs_auth':
                # Only notify once per day for auth issues
                if self._should_notify_auth_issue():
                    critical_issues.append(f"🔐 User Monitor: Authentication required")
        
        return critical_issues
    
    def _should_notify_auth_issue(self) -> bool:
        """Check if we should notify about auth issues (rate limiting)"""
        last_auth_notification = getattr(self, '_last_auth_notification', None)
        if not last_auth_notification:
            self._last_auth_notification = datetime.now()
            return True
        
        # Notify at most once per 6 hours for auth issues
        if datetime.now() - last_auth_notification > timedelta(hours=6):
            self._last_auth_notification = datetime.now()
            return True
        
        return False
    
    async def _notify_admin_of_issues(self, critical_issues: List[str], context):
        """Notify admin of critical issues"""
        if not context or not context.bot:
            return
        
        try:
            # Rate limiting - don't spam admin
            last_notification = getattr(self, '_last_critical_notification', None)
            if last_notification and datetime.now() - last_notification < timedelta(hours=1):
                return  # Don't notify more than once per hour
            
            self._last_critical_notification = datetime.now()
            
            message = "🚨 **System Health Alert**\n\n"
            message += "\n".join(critical_issues)
            message += f"\n\nUse `/admin health` for detailed status."
            
            await asyncio.wait_for(
                context.bot.send_message(
                    chat_id=self.config.AUTHORIZED_ADMIN_ID,
                    text=message,
                    parse_mode='Markdown'
                ),
                timeout=self.config.TELEGRAM_API_TIMEOUT
            )
            
            logger.info(f"Critical health issues notified to admin: {len(critical_issues)} issues")
            
        except Exception as e:
            logger.error(f"Failed to notify admin of critical issues: {e}")
    
    def _log_health_summary(self, overall_status: str, results: Dict):
        """Log health check summary"""
        if overall_status == 'healthy':
            logger.debug("🏥 Health check: All systems healthy")
        else:
            issue_count = sum(
                len(result.get('issues', [])) 
                for result in results.values() 
                if isinstance(result, dict)
            )
            logger.info(f"🏥 Health check: Status {overall_status}, {issue_count} issues found")
    
    # =============================================================================
    # PUBLIC METHODS FOR ADMIN COMMANDS
    # =============================================================================
    
    async def get_detailed_health_report(self) -> Dict:
        """Get detailed health report for admin commands"""
        try:
            # Force a fresh health check
            results = await self._perform_comprehensive_health_check(None)
            overall_status = self._determine_overall_status(results)
            
            return {
                'overall_status': overall_status,
                'last_check': self.last_health_check.isoformat() if self.last_health_check else None,
                'components': results,
                'summary': self._generate_health_summary(results)
            }
            
        except Exception as e:
            logger.error(f"Error generating health report: {e}")
            return {
                'overall_status': 'error',
                'error': str(e),
                'last_check': None,
                'components': {},
                'summary': 'Health report generation failed'
            }
    
    def _generate_health_summary(self, results: Dict) -> str:
        """Generate human-readable health summary"""
        try:
            summary_parts = []
            
            for component, result in results.items():
                if not isinstance(result, dict):
                    continue
                
                status = result.get('status', 'unknown')
                
                if component == 'database':
                    response_time = result.get('response_time_ms', 0)
                    summary_parts.append(f"Database: {status} ({response_time:.1f}ms)")
                    
                elif component == 'user_monitor':
                    auth_status = result.get('auth_status', 'unknown')
                    channels = result.get('monitored_channels', 0)
                    summary_parts.append(f"User Monitor: {status} ({auth_status}, {channels} channels)")
                    
                elif component == 'channels':
                    valid = result.get('valid_channels', 0)
                    total = result.get('sample_checked', 0)
                    summary_parts.append(f"Channels: {status} ({valid}/{total} validated)")
                    
                elif component == 'system':
                    memory = result.get('memory_usage_percent', 0)
                    cpu = result.get('cpu_usage_percent', 0)
                    summary_parts.append(f"System: {status} (Memory: {memory:.1f}%, CPU: {cpu:.1f}%)")
            
            return "; ".join(summary_parts)
            
        except Exception as e:
            return f"Summary generation failed: {str(e)}"
    
    async def get_performance_metrics(self) -> Dict:
        """Get current performance metrics"""
        try:
            return await self._check_performance_metrics()
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {'error': str(e)}
    
    def get_component_status(self, component_name: str) -> Optional[Dict]:
        """Get status of specific component"""
        return self.component_status.get(component_name)
    
    def is_system_healthy(self) -> bool:
        """Quick check if system is healthy"""
        if not self.component_status:
            return False  # No health data available
        
        overall_status = self._determine_overall_status(self.component_status)
        return overall_status in ['healthy', 'warning']