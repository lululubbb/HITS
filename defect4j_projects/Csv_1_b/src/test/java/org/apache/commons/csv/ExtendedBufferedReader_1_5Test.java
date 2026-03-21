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

class ExtendedBufferedReader_1_5Test {

    private Reader mockReader;
    private ExtendedBufferedReader extendedBufferedReader;

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
        int first = extendedBufferedReader.read();
        int second = extendedBufferedReader.read();
        assertEquals('a', first);
        assertEquals(-1, second);
    }

    @Test
    @Timeout(8000)
    void testReadAgain() throws IOException, NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);

        when(mockReader.read()).thenReturn((int) 'b', -1);
        int firstCall = (int) readAgainMethod.invoke(extendedBufferedReader);
        int secondCall = (int) readAgainMethod.invoke(extendedBufferedReader);

        assertEquals('b', firstCall);
        assertEquals(-1, secondCall);
    }

    @Test
    @Timeout(8000)
    void testReadCharArray() throws IOException {
        char[] buffer = new char[5];
        when(mockReader.read(buffer, 0, 5)).thenAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            String s = "hello";
            for (int i = 0; i < s.length(); i++) {
                buf[off + i] = s.charAt(i);
            }
            return s.length();
        });

        int readCount = extendedBufferedReader.read(buffer, 0, 5);
        assertEquals(5, readCount);
        assertArrayEquals("hello".toCharArray(), buffer);
    }

    @Test
    @Timeout(8000)
    void testReadLine() throws IOException {
        when(mockReader.read()).thenReturn((int) 'h', (int) 'i', (int) '\n', -1);
        String line = extendedBufferedReader.readLine();
        assertEquals("hi", line);
    }

    @Test
    @Timeout(8000)
    void testLookAhead() throws IOException, NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        when(mockReader.read()).thenReturn((int) 'x', -1);
        int firstLook = (int) lookAheadMethod.invoke(extendedBufferedReader);
        int secondLook = (int) lookAheadMethod.invoke(extendedBufferedReader);

        assertEquals('x', firstLook);
        assertEquals('x', secondLook);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber() throws IOException {
        assertEquals(0, extendedBufferedReader.getLineNumber());

        when(mockReader.read()).thenReturn((int) 'a', (int) '\n', -1);
        extendedBufferedReader.readLine();
        assertEquals(1, extendedBufferedReader.getLineNumber());
    }
}