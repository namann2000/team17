#! /usr/bin/env python3

# Import the core Python modules for ROS and to implement ROS Actions:
import rospy
import actionlib
import time 

# Import some image processing modules:
import cv2
from cv_bridge import CvBridge, CvBridgeError

# Import all the necessary ROS message types:
from sensor_msgs.msg import Image, LaserScan
from com2009_msgs.msg import SearchFeedback, SearchResult, SearchAction, SearchGoal

# Import the tb3 modules (which needs to exist within the "week6_vision" package)
from tb3 import Tb3Move #, Tb3LaserScan, Tb3Odometry
from tb3 import Tb3LaserScan, Tb3Odometry
import numpy as np
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from tf.transformations import euler_from_quaternion
from math import pi, sqrt, pow
from statistics import mean


class colour_search(object):

    feedback = SearchFeedback() 
    result = SearchResult()

    def __init__(self):
        node_name = "beaconing"
        rospy.init_node(node_name)
        self.startup = True
        self.turn = False
        self.odom_subscriber = rospy.Subscriber('odom', Odometry, self.odom_callback)
        self.camera_subscriber = rospy.Subscriber("/camera/rgb/image_raw", Image, self.camera_callback)
        self.robot_controller = Tb3Move()
        self.robot_odometry = Tb3Odometry()
        self.robot_lidar = Tb3LaserScan()
        self.cvbridge_interface = CvBridge()
        
        #self.rate = rospy.Rate(1) # hz
        self.vel = Twist()
        self.start_colour = ""
        self.move_rate = "" # fast, slow or stop
        self.stop_counter = 0
        
        self.turn_vel_fast = -0.5
        self.turn_vel_slow = -0.3
        self.robot_controller.set_move_cmd(0.0, 0.0)
        self.ctrl_c = False
        rospy.on_shutdown(self.shutdown_ops)
        rospy.loginfo(f"the {node_name} node has been initialised...")
        self.rate = rospy.Rate(5)
        
        self.m00 = 0
        self.m00_min = 100000

        self.pub = rospy.Publisher('cmd_vel', Twist, queue_size=10)
        
        self.rate = rospy.Rate(10) # hz

        self.blue_lower = np.array([115, 224, 100])
        self.blue_upper = np.array([130, 255, 255])
        self.red_lower = np.array([0, 185, 100])
        self.red_upper = np.array([10, 255, 255])
        self.green_lower = np.array([35, 150, 100])
        self.green_higher = np.array([70, 255, 255])
        self.turquoise_lower = np.array([75, 150, 100])
        self.turquoise_upper = np.array([100, 255, 255])
        self.yellow_lower = np.array([20, 100, 100])
        self.yellow_upper = np.array([30, 255, 255])
        self.purple_lower = np.array([135, 100, 100])
        self.purple_upper = np.array([160, 255, 255])

        self.blue_mask = 0
        self.red_mask = 0
        self.green_mask = 0
        self.turquoise_mask = 0
        self.yellow_mask = 0 
        self.purple_mask = 0

        self.x = 0.0
        self.y = 0.0
        self.theta_z = 0.0
        # variables to use for the "reference position":
        self.x0 = 0.0
        self.y0 = 0.0
        self.theta_z0 = 0.0

        self.frontDistance=0.0
        self.rightDistance=0.0
        self.leftDistance=0.0
        self.maxDistance=0.0
        self.turnDirection="NONE"

        # self.actionserver = actionlib.SimpleActionServer("/search_action_server", 
        #     SearchAction, self.main, auto_start=False)
        # self.actionserver.start()

    def shutdown_ops(self):
        self.robot_controller.stop()
        cv2.destroyAllWindows()
        self.pub.publish(Twist())
        self.ctrl_c = True
    
    def laser_function(self, laser_data):
        self.frontDistance = min(laser_data.ranges[:20] + laser_data.ranges[340:359])
        self.leftDistance = mean(laser_data.ranges[70:120])
        self.rightDistance = mean(laser_data.ranges[240:290])
        self.maxDistance = max(laser_data.ranges[0:180])
        self.minRight = min(laser_data.ranges[230:300])
        self.minLeft = min(laser_data.ranges[60:130])

    def print_stuff(self, a_message):
    # a function to print information to the terminal (use as you wish):
    # print the message that has been passed in to the method via the "a_message" input:
        print(a_message)
    
    # you could use this to print the current velocity command:
    #print(f"current velocity: lin.x = {self.vel.linear.x:.1f}, ang.z = {self.vel.angular.z:.1f}")
    # you could also print the current odometry to the terminal here, if you wanted to:
    #print(f"current odometry: x = {self.x:.3f}, y = {self.y:.3f}, theta_z = {self.theta_z:.3f}")



    def camera_callback(self, img_data):
        try:
            cv_img = self.cvbridge_interface.imgmsg_to_cv2(img_data, desired_encoding="bgr8")
        except CvBridgeError as e:
            print(e)
        
        height, width, _ = cv_img.shape
        crop_width = width - 800
        crop_height = 400
        crop_x = int((width/2) - (crop_width/2))
        crop_y = int((height/2) - (crop_height/2))

        crop_img = cv_img[crop_y:crop_y+crop_height, crop_x:crop_x+crop_width]
        hsv_img = cv2.cvtColor(crop_img, cv2.COLOR_BGR2HSV)


        # create a single mask to accommodate all six dectection colours:
        # for i in range(6):
        #     if i == 0:
        #         mask = cv2.inRange(hsv_img, self.lower[i], self.upper[i])
        #     else:
        #         mask = mask + cv2.inRange(hsv_img, self.lower[i], self.upper[i])

        # colour = cv2.bitwise_and(hsv_img, hsv_img, mask = mask)

        # m = cv2.moments(mask)

        # colour masks
        self.blue_mask = cv2.inRange(hsv_img, self.blue_lower, self.blue_upper)
        self.red_mask = cv2.inRange(hsv_img, self.red_lower, self.red_upper)
        self.green_mask = cv2.inRange(hsv_img, self.green_lower, self.green_higher)
        self.turquoise_mask = cv2.inRange(hsv_img, self.turquoise_lower, self.turquoise_upper)
        self.yellow_mask = cv2.inRange(hsv_img, self.yellow_lower, self.yellow_upper)
        self.purple_mask = cv2.inRange(hsv_img, self.purple_lower, self.purple_upper)
        # self.m00 = m["m00"]
        # self.cy = m["m10"] / (m["m00"] + 1e-5)

        # if self.m00 > self.m00_min:
        #     cv2.circle(crop_img, (int(self.cy), 200), 10, (0, 0, 255), 2)
        
        # cv2.imshow("cropped image", crop_img)
        cv2.waitKey(1)

    def odom_callback(self, odom_data):
        # obtain the orientation and position co-ords:
        or_x = odom_data.pose.pose.orientation.x
        or_y = odom_data.pose.pose.orientation.y
        or_z = odom_data.pose.pose.orientation.z
        or_w = odom_data.pose.pose.orientation.w
        pos_x = odom_data.pose.pose.position.x
        pos_y = odom_data.pose.pose.position.y

        # convert orientation co-ords to roll, pitch & yaw (theta_x, theta_y, theta_z):
        (roll, pitch, yaw) = euler_from_quaternion([or_x, or_y, or_z, or_w], 'sxyz')
        
        self.x = pos_x
        self.y = pos_y
        self.theta_z = yaw 

        #initialising and storing starting odom readings
        if self.startup:
            self.startup = False
            self.x0 = self.x
            self.y0 = self.y
            self.theta_z0 = self.theta_z
    
    def turn_left(self):
        left_distance = self.robot_lidar.left_min
        right_distance = self.robot_lidar.right_min
        if left_distance > right_distance:
            return True


    def turn_right(self):
        left_distance = self.robot_lidar.left_min
        right_distance = self.robot_lidar.right_min
        if left_distance < right_distance:
            return True

    def main(self):
        searchInitiated = False # flag for printing colour detected message once
        beaconingInitiated = False # flag for beaconing sequence
        searchColour = ''
        beaconTarget = 0 # will store current value of the mask we are searching for
        beaconColor = 0 # will store value of mask that needs to be found
        searching = False # flag for searching for beacon
        detectingColor = True # flag for detecting initial colour
        startTime = time.time()
        status = ""
        wait = 0
        while not self.ctrl_c:
            # detect beacon colour
            while detectingColor:
                currentTime = time.time()
                if int(currentTime - startTime) > 23:
                    self.robot_controller.set_move_cmd(0.15, 0)
                    self.robot_controller.publish()
                    if int(currentTime - startTime) > 26:
                        searching = True
                        detectingColor = False
                else:
                    self.robot_controller.set_move_cmd(0.0, self.turn_vel_slow)
                    self.robot_controller.publish()
                
                if int(currentTime - startTime) > 9 and int(currentTime - startTime) < 11:
                    pastHalfway = True
                    if searchColour == '':
                        
                        searchBlue = np.sum(self.blue_mask)
                        if searchBlue > 0:
                            searchColour = 'Blue'
                            beaconColor = searchBlue
                        searchRed = np.sum(self.red_mask)
                        if searchRed > 0:
                            searchColour = 'Red'
                            beaconColor = searchRed
                        searchGreen = np.sum(self.green_mask)
                        if searchGreen > 0:
                            searchColour = 'Green'
                            beaconColor = searchGreen
                        searchTurquoise = np.sum(self.turquoise_mask)
                        if searchTurquoise > 0:
                            searchColour = 'Turquoise'
                            beaconColor = searchTurquoise
                        searchYellow = np.sum(self.yellow_mask)
                        if searchYellow > 0:
                            searchColour = 'Yellow'
                            beaconColor = searchYellow
                        searchPurple = np.sum(self.purple_mask)
                        if searchPurple > 0:
                            searchColour = 'Purple'
                            beaconColor = searchPurple
            
                if not searchInitiated and searchColour != '':
                    print('SEARCH INITIATED: The target beacon colour is ' + searchColour + '.')
                    searchInitiated = True
            
            # search for beacon of colour 'searchColour'
            while searching:
            
                if searchColour == 'Blue':
                        beaconTarget = self.blue_mask
                if searchColour == 'Red':
                        beaconTarget = self.red_mask
                if searchColour == 'Green':
                        beaconTarget = self.green_mask
                if searchColour == 'Turquoise':
                        beaconTarget = self.turquoise_mask
                if searchColour == 'Yellow':
                        beaconTarget = self.yellow_mask
                if searchColour == 'Purple':
                        beaconTarget = self.purple_mask

                findThis = np.sum(beaconTarget)
                
                self.posx0 = self.robot_odometry.posx
                self.posy0 = self.robot_odometry.posy
                    
                

                if self.startup:
                    self.vel = Twist()
                    status = "init"
                elif self.turn:
                    if abs(self.theta_z0 - self.theta_z) >= pi/2 and wait > 5:
                        # If the robot has turned 90 degrees (in radians) then stop turning
                        self.turn = False
                        self.vel = Twist()
                        self.theta_z0 = self.theta_z
                        status = "turn-fwd transition"
                        wait = 0

                if self.frontDistance > 0.535:
                    self.turnDirection="NONE"
                    self.print_stuff("Forward distance {}".format(self.frontDistance))


                    # more space in front
                    
                    self.vel.linear.x=0.25
                    self.vel.angular.z = 0


                else:
                    self.vel.linear.x=0
                    rospy.sleep(1)
                    if  self.turnDirection == "NONE":
                        
                            
                        if self.rightDistance < self.leftDistance:
                            print("entered left loop")
                            startTime = time.time()
                            for i in range(500):
                                self.turnDirection="LEFT"
                                self.vel.linear.x = 0
                                self.vel.angular.z = 0.2
                                self.pub.publish(self.vel) 
                                self.print_stuff("TURN DECISION LEFT")
                        

                        else:
                            print("entered right loop")
                            startTime = time.time()
                            for i in range(100):
                                self.turnDirection="RIGHT"
                                self.vel.linear.x = 0
                                self.vel.angular.z = -0.2
                                self.pub.publish(self.vel)
                                self.print_stuff("TURN DECISION RIGHT")
                            rospy.sleep(4)
                            for i in range(40):
                                self.vel.linear.x  = 0.1
                    
                        self.turnDirection = "NONE"
                   
                        




            

            ##########################
            
            
                # publish whatever velocity command has been set in your code above:
                    self.pub.publish(self.vel)
                        # call a function which prints some information to the terminal:
                        #self.print_stuff("this is a message that has been passed to the 'print_stuff()' method")
                        # maintain the loop rate @ 10 hz
                    self.rate.sleep()

                    self.vel.linear.x = 0.26
                            
                if findThis > 0 and time.time() > (startTime + 60):
                    print('TARGET DETECTED: Beaconing Initiated.')
                    self.robot_controller.set_move_cmd(0, 0)
                    self.robot_controller.publish()
                    searching = False
                    beaconingInitiated = True
                        
            # initiate beaconing
            while beaconingInitiated:
                if self.robot_lidar.min_distance < 0.2:
                    self.robot_controller.set_move_cmd(0.0, 0.0)
                    self.robot_controller.publish()
                    print("BEACONING COMPLETE: The robot has now stopped.")
                    beaconingInitiated = False
                self.robot_controller.set_move_cmd(0.1, 0)
                self.robot_controller.publish()

            self.robot_controller.set_move_cmd(0.0, 0.0)
            self.robot_controller.publish()
            self.rate.sleep()
            
if __name__ == "__main__":
    search_instance = colour_search()
    try:
        search_instance.main()
    except rospy.ROSInterruptException:
        pass