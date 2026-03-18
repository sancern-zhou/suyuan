@echo off
echo ============================================
echo EKMA场景预计算 - 运行中...
echo ============================================
echo.
echo 预计算3个典型场景 (约10-15分钟)
echo ============================================
echo.

cd /d "%~dp0"

python -c "import sys; sys.path.insert(0, '.'); from app.tools.analysis.pybox_integration.cache_utils import EKMA_Scenes, precompute_all_scenes, get_cache_statistics; from app.tools.analysis.pybox_integration.pybox_adapter import PyBoxAdapter; print('初始化PyBox...'); pybox = PyBoxAdapter(mechanism='RACM2'); print('开始预计算...'); scenes = EKMA_Scenes.get_all_scene_keys(); total = len(scenes); import sys; results = {}; [results.update(precompute_all_scenes(pybox, scenes=[s], grid_size=21, simulation_time=25200.0, progress_callback=lambda c,t,m: sys.stdout.write('\\r  [%d/%d] 场景 %s   ' % (c,t,m)))) or print() for s in scenes]; print('\\n预计算完成!'); [print('  [%s] %s - %s' % (k, EKMA_Scenes.SCENES[k]['name'], results.get(k,{}).get('status','?'))) for k in scenes]; stats = get_cache_statistics('app/tools/analysis/pybox_integration/o3_surface_cache'); print('  缓存: %d 文件, %s MB' % (stats['total_files'], stats['total_size_mb']))"

echo.
pause
