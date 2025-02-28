import datetime
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.db import transaction
from .models import User, Produce
from .forms import CropRecommendationForm, FertilizerPredictionForm, UserInputForm, CropProduceListForm
import pickle
import numpy as np
from django.template.defaulttags import register
from .functions import getWeatherDetails, getAgroNews, getFertilizerRecommendation, getMarketPricesAllStates, GetResponse
import base64
import os
from google import genai
from google.genai import types
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Load models once at startup with error handling
try:
    cropRecommendationModel = pickle.load(open('model_code/CropRecommend.pkl', 'rb'))
    fertilizerRecommendModel = pickle.load(open('model_code/Fertilizer.pkl', 'rb'))
except Exception as e:
    logger.error(f"Failed to load models: {str(e)}")
    cropRecommendationModel = None
    fertilizerRecommendModel = None

@register.filter
def get_range(value):
    return range(value)

@register.filter
def index(indexable, i):
    return indexable[i]

def getDetailsFromUID(id):
    cache_key = f'user_{id}'
    user = cache.get(cache_key)
    if not user:
        try:
            user = User.objects.get(id=id)
            cache.set(cache_key, user, timeout=300)  # Cache for 5 minutes
        except User.DoesNotExist:
            logger.error(f"User with id {id} not found")
            raise
    return user

def e404_page(request):
    error_message = request.session.get("error_message", "An error occurred")
    return render(request, "dash/404.html", {"errormsg": error_message})

def home_page(request):
    try:
        id = request.session.get("member_logged_id")
        if not id:
            raise ValueError("User not logged in")

        userlogged = getDetailsFromUID(id)
        
        my_products = Produce.objects.filter(farmerid=userlogged.id)
        public_products = Produce.objects.all()
        
        # Cache expensive operations
        weather_cache_key = f'weather_{userlogged.coords}'
        details = cache.get(weather_cache_key)
        if not details:
            details = getWeatherDetails(userlogged.coords)
            cache.set(weather_cache_key, details, timeout=3600)  # Cache for 1 hour

        news_cache_key = 'agro_news'
        news = cache.get(news_cache_key)
        if not news:
            news = getAgroNews()
            cache.set(news_cache_key, news, timeout=86400)  # Cache for 24 hours

        context = {
            "user": userlogged,
            "produces": my_products,
            "produces_count": my_products.count(),
            "public_produces_count": public_products.count(),
            "last_listing": my_products.last() if my_products.exists() else "",
            'news': news[:3],
            'weather': details,
        }
        return render(request, 'dash/home.html', context)
    except Exception as e:
        logger.error(f"Home page error: {str(e)}")
        request.session["error_message"] = "An unexpected error occurred"
        return redirect('/admin/404/')

def forum(request):
    try:
        id = request.session.get("member_logged_id")
        if not id:
            raise ValueError("User not logged in")
        return render(request, 'dash/forum.html')
    except Exception as e:
        logger.error(f"Forum error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def croprec(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        form = CropRecommendationForm(request.POST if request.method == 'POST' else None)
        
        if request.method == 'POST' and form.is_valid():
            weatherd = getWeatherDetails(userlogged.coords)
            try:
                data = np.array([[
                    form.cleaned_data['nitrogen'],
                    form.cleaned_data['phosphorus'],
                    form.cleaned_data['potassium'],
                    weatherd[1],  # temp
                    weatherd[2],  # humidity
                    form.cleaned_data['PH'],
                    form.cleaned_data['rainfall']
                ]])
                prediction = cropRecommendationModel.predict(data)
                context = {
                    'form': form,
                    'user': userlogged,
                    'userid': userlogged.id,
                    'prediction': prediction[0]
                }
            except Exception as e:
                logger.error(f"Crop recommendation prediction error: {str(e)}")
                context = {
                    'form': form,
                    'user': userlogged,
                    'userid': userlogged.id,
                    'error': "Prediction failed"
                }
        else:
            context = {
                "form": form,
                'userid': userlogged.id,
                'user': userlogged,
            }
        return render(request, 'dash/tools/crop_rec.html', context)
    except Exception as e:
        logger.error(f"Crop recommendation error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def news_page(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        news_cache_key = 'agro_news'
        news = cache.get(news_cache_key)
        if not news:
            news = getAgroNews()
            cache.set(news_cache_key, news, timeout=86400)
            
        context = {
            'news': news,
            'user': userlogged,
            'userid': userlogged.id,
        }
        return render(request, 'dash/news.html', context)
    except Exception as e:
        logger.error(f"News page error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def fertrec(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        form = FertilizerPredictionForm(request.POST if request.method == 'POST' else None)
        
        if request.method == 'POST' and form.is_valid():
            weatherd = getWeatherDetails(userlogged.coords)
            try:
                prediction = getFertilizerRecommendation(
                    fertilizerRecommendModel,
                    form.cleaned_data['nitrogen'],
                    form.cleaned_data['phosphorus'],
                    form.cleaned_data['potassium'],
                    weatherd[1],  # temp
                    weatherd[2],  # humidity
                    form.cleaned_data['moisture'],
                    form.cleaned_data['soil_type'],
                    form.cleaned_data['crop']
                )
                context = {
                    'form': form,
                    'user': userlogged,
                    'userid': userlogged.id,
                    'prediction': prediction
                }
            except Exception as e:
                logger.error(f"Fertilizer recommendation error: {str(e)}")
                context = {
                    'form': form,
                    'user': userlogged,
                    'userid': userlogged.id,
                    'error': "Prediction failed"
                }
        else:
            context = {
                "form": form,
                "user": userlogged,
                'userid': userlogged.id,
            }
        return render(request, 'dash/tools/fert_rec.html', context)
    except Exception as e:
        logger.error(f"Fertilizer recommendation error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def crop_prices_page(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        prices_cache_key = f'prices_{logged_id}'
        latest_prices = cache.get(prices_cache_key)
        if not latest_prices:
            latest_prices = getMarketPricesAllStates()
            cache.set(prices_cache_key, latest_prices, timeout=3600)
            
        context = {
            "userid": userlogged.id,
            "user": userlogged,
            "date": datetime.datetime.now(),
            "prices": latest_prices
        }
        return render(request, 'dash/check_prices.html', context)
    except Exception as e:
        logger.error(f"Crop prices error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def help_page(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        form = UserInputForm(request.POST if request.method == 'POST' else None)
        
        if request.method == 'POST' and form.is_valid():
            try:
                if 'chatlog' in request.session:
                    del request.session['chatlog']
                    
                query = form.cleaned_data['userinput']
                res = GetResponse(query)
                
                chatlog = request.session.get('chatlog', {'queries': [], 'responses': []})
                chatlog['queries'].append(query)
                chatlog['responses'].append(res)
                request.session['chatlog'] = chatlog
                
                context = {
                    'userid': userlogged.id,
                    'user': userlogged,
                    'log': chatlog,
                    'form': form,
                }
            except Exception as e:
                logger.error(f"Help page processing error: {str(e)}")
                context = {
                    'userid': userlogged.id,
                    'user': userlogged,
                    'form': form,
                    'error': "Failed to process request"
                }
        else:
            context = {
                "userid": userlogged.id,
                'form': form,
                "user": userlogged,
            }
        return render(request, 'dash/help.html', context)
    except Exception as e:
        logger.error(f"Help page error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def profile_page(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        context = {
            "userid": userlogged.id,
            "user": userlogged,
        }
        return render(request, 'dash/profile.html', context)
    except Exception as e:
        logger.error(f"Profile page error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def logout_view(request):
    try:
        if 'member_logged_id' in request.session:
            del request.session["member_logged_id"]
            return redirect('/')
        else:
            raise ValueError("Not logged in")
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        request.session["error_message"] = "You are not logged in yet."
        return redirect('/admin/404/')

def list_page(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        
        form = CropProduceListForm(request.POST if request.method == 'POST' else None)
        
        if request.method == 'POST' and form.is_valid():
            try:
                Produce.objects.create(
                    **form.cleaned_data,
                    farmerid=int(userlogged.id),
                    unit="quintals"
                )
                context = {
                    'form': form,
                    'user': userlogged,
                    'userid': userlogged.id,
                    'success': "Your produce has been listed."
                }
            except Exception as e:
                logger.error(f"Listing creation error: {str(e)}")
                context = {
                    'form': form,
                    'user': userlogged,
                    'userid': userlogged.id,
                    'error': "Failed to list produce"
                }
        else:
            context = {
                "form": form,
                'userid': userlogged.id,
                'user': userlogged,
            }
        return render(request, "dash/market/list_produce.html", context)
    except Exception as e:
        logger.error(f"List page error: {str(e)}")
        request.session["error_message"] = "Please login to continue"
        return redirect('/admin/404/')

def check_my_listings(request):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        produces = Produce.objects.filter(farmerid=userlogged.id)
        
        context = {
            'user': userlogged,
            'produces': produces
        }
        return render(request, "dash/market/check_produces.html", context)
    except Exception as e:
        logger.error(f"Check listings error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def delete_listing(request, id):
    try:
        logged_id = request.session.get("member_logged_id")
        if not logged_id:
            raise ValueError("User not logged in")
            
        userlogged = getDetailsFromUID(logged_id)
        listing = Produce.objects.get(id=id, farmerid=userlogged.id)
        listing.delete()
        return redirect('/admin/check_products')
    except Exception as e:
        logger.error(f"Delete listing error: {str(e)}")
        request.session["error_message"] = "Please Login to Continue"
        return redirect('/admin/404/')

def layout_dashboard(request):
    return render(request, 'dash/layout_dashboard.html')