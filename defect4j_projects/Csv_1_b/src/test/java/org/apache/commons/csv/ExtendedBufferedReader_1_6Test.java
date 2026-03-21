package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_1_6Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testConstructor() {
        assertNotNull(extendedBufferedReader);
    }

    @Test
    @Timeout(8000)
    void testRead() throws IOException {
        when(mockReader.read()).thenReturn((int) 'a', -1);
        int firstRead = extendedBufferedReader.read();
        assertEquals('a', firstRead);
        int secondRead = extendedBufferedReader.read();
        assertEquals(-1, secondRead);
    }

    @Test
    @Timeout(8000)
    void testReadAgain() throws NoSuchMethodException, SecurityException, IllegalAccessException, IllegalArgumentException, InvocationTargetException, IOException {
        when(mockReader.read()).thenReturn((int) 'b');
        Method readAgain = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgain.setAccessible(true);
        int result = (int) readAgain.invoke(extendedBufferedReader);
        assertEquals('b', result);
    }

    @Test
    @Timeout(8000)
    void testReadCharArray() throws IOException {
        char[] buf = new char[10];
        when(mockReader.read(buf, 0, 10)).thenReturn(5);
        int readCount = extendedBufferedReader.read(buf, 0, 10);
        assertEquals(5, readCount);
    }

    @Test
    @Timeout(8000)
    void testReadLine() throws IOException {
        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenAnswer(invocation -> {
            char[] buffer = invocation.getArgument(0);
            buffer[0] = 't';
            buffer[1] = 'e';
            buffer[2] = 's';
            buffer[3] = 't';
            return 4;
        });
        String line = extendedBufferedReader.readLine();
        assertNotNull(line);
        assertEquals("test", line);
    }

    @Test
    @Timeout(8000)
    void testLookAhead() throws NoSuchMethodException, SecurityException, IllegalAccessException, IllegalArgumentException, InvocationTargetException, IOException {
        when(mockReader.read()).thenReturn((int) 'c');
        Method lookAhead = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAhead.setAccessible(true);
        int result = (int) lookAhead.invoke(extendedBufferedReader);
        assertEquals('c', result);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber() throws NoSuchMethodException, SecurityException, IllegalAccessException, IllegalArgumentException, InvocationTargetException {
        Method getLineNumber = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumber.setAccessible(true);
        int lineNumber = (int) getLineNumber.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);
    }
}